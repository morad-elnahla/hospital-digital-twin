"""AI Hospital Digital Twin - agents + dashboard server.

    python app.py [--port 8000] [--data data] [--reset-credentials]     then open http://127.0.0.1:8000

Standard library only. Serves the dashboard (dashboard.html + static/) and a JSON API over the CSV
data pack. Every endpoint except /api/login needs a signed-in account; the role comes from the
account stored on the server, never from the request. Decisions, the sandbox, the audit log and
accounts are persisted in ./runtime; structured policies in ./policies. Nothing writes to data/.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from hospital_agents import Orchestrator, Settings, insights, llm
from hospital_agents.assistant import Assistant
from hospital_agents.audit import InMemoryAudit, JsonlAudit
from hospital_agents.auth import PERMISSIONS, Auth, AuthError, Principal
from hospital_agents.contracts import (PoolAdjustment, Reschedule, Proposal, SlotKey, PolicyBundle,
                                       action_from_dict, invert, to_jsonable)
from hospital_agents.arbitration import Arbitrator
from hospital_agents.explain import TemplateExplainer
from hospital_agents.localize import decision_texts, has_sandbox_effect, no_action_reason, overlay, reason_codes
from hospital_agents.card import describe
from hospital_agents.messages import Msg, codes, render
from hospital_agents.policies import CompositeRetriever, CorpusRetriever, FolderPolicyRetriever
from hospital_agents.ports import AuditEvent
from hospital_agents.store import DecisionStore, atomic_write
from hospital_agents.twin_data import BED_UNITS, Scenario, TwinData, apply_actions

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CONTENT_TYPES = {".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".woff2": "font/woff2"}
CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


class App:
    def __init__(self, data_dir: Path, runtime: Path = ROOT / "runtime", policy_dir: Path = ROOT / "policies") -> None:
        self.data_dir, self.runtime, self.policy_dir = Path(data_dir), Path(runtime), Path(policy_dir)
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.policy_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.twin = TwinData(self.data_dir)
        corpus = self.data_dir / "combined.json"
        self.corpus = CorpusRetriever(corpus) if corpus.exists() else None
        self.audit = JsonlAudit(self.runtime / "audit.jsonl")
        self.auth = Auth(self.runtime / "users.json")
        self.store = DecisionStore(self.runtime)
        self.drafts_path = self.runtime / "scenario_drafts.json"
        self.scenario_drafts = json.loads(self.drafts_path.read_text(encoding="utf-8")) if self.drafts_path.exists() else {}
        self.assistant = Assistant(self)
        self._alert_cache: dict[tuple, dict] = {}

    @property
    def applied(self):
        return self.store.applied

    # ───────────── helpers ─────────────
    def log(self, actor: str, action: str, version: str = "", **detail) -> None:
        self.audit.record(AuditEvent(actor, action, datetime.now(timezone.utc), version, to_jsonable(detail)))

    @staticmethod
    def _need(principal: Principal | None, permission: str) -> Principal:
        try:
            return Auth.require(principal, permission)
        except AuthError as e:
            raise ApiError(HTTPStatus(e.status), e.message) from None

    def parse_as_of(self, raw: str | None) -> datetime:
        try:
            as_of = datetime.fromisoformat(raw).replace(minute=0, second=0, microsecond=0) if raw else self.twin.default_as_of
        except (ValueError, TypeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "as_of must be an ISO datetime") from None
        lo, hi = datetime.fromisoformat(self.twin.first_day), datetime.fromisoformat(self.twin.last_day)
        if not lo <= as_of <= hi.replace(hour=23):
            raise ApiError(HTTPStatus.BAD_REQUEST, f"as_of must lie within {lo.date()} and {hi.date()}")
        return as_of

    def parse_scenario(self, body: dict) -> Scenario:
        unit = body.get("unit", "ICU")
        try:
            mult = float(body.get("multiplier", body.get("demand_multiplier", 1.0)))
        except (TypeError, ValueError):
            mult = math.nan
        if unit not in ("ER", "ICU", "WARD") or not (math.isfinite(mult) and 0.1 <= mult <= 50):
            raise ApiError(HTTPStatus.BAD_REQUEST, "unit must be ER, ICU or WARD and multiplier within 0.1-50")
        horizon = body.get("horizon", 7)
        seed = body.get("seed", 0)
        if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 30:
            raise ApiError(HTTPStatus.BAD_REQUEST, "horizon must be an integer from 1 to 30 days")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**31 - 1:
            raise ApiError(HTTPStatus.BAD_REQUEST, "seed must be an integer from 0 to 2147483647")
        interventions = body.get("interventions", [])
        if not isinstance(interventions, list) or len(interventions) > 100:
            raise ApiError(HTTPStatus.BAD_REQUEST, "interventions must be a list with at most 100 entries")
        normalized = []
        for i, raw in enumerate(interventions):
            if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
                raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] must be an object with a type")
            kind = raw["type"]
            item = dict(raw)
            if kind == "demand_change":
                u = item.get("unit")
                x = item.get("x")
                if u not in ("ER", "ICU", "WARD") or isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0.1 <= x <= 50:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] demand_change requires unit ER/ICU/WARD and x from 0.1 to 50")
            elif kind == "er_arrivals_surge":
                x = item.get("x")
                if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0.1 <= x <= 50:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] er_arrivals_surge requires x from 0.1 to 50")
            elif kind == "staff_change":
                u, role = item.get("unit"), item.get("role")
                if u not in BED_UNITS or role not in ("NURSE", "DOCTOR") or ("delta" in item) == ("absent_pct" in item):
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] staff_change requires unit ER/ICU/WARD, role NURSE/DOCTOR, and exactly one of delta or absent_pct")
                value = item.get("delta", item.get("absent_pct"))
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] staff_change value must be finite")
                if "delta" in item and (not isinstance(value, int) or not -1000 <= value <= 1000):
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] staff delta must be an integer from -1000 to 1000")
                if "absent_pct" in item and not 0 <= value <= 100:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] absent_pct must be from 0 to 100")
            elif kind == "bed_change":
                d = item.get("delta")
                if item.get("unit") not in BED_UNITS or isinstance(d, bool) or not isinstance(d, int) or not -1000 <= d <= 1000:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] bed_change requires unit ER/ICU/WARD and integer delta from -1000 to 1000")
            elif kind == "or_closed":
                dates = item.get("dates", [])
                if not isinstance(dates, list) or not dates or any(not isinstance(d, str) for d in dates):
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] or_closed requires a non-empty dates list")
                try:
                    for d in dates: datetime.fromisoformat(d)
                except ValueError:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] dates must be ISO dates") from None
                if item.get("or_id") is not None and (not isinstance(item["or_id"], str) or not item["or_id"]):
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] or_id must be a non-empty string")
                known_rooms = {r["or_id"] for r in self.twin.t["operating_rooms"]}
                if item.get("or_id") is not None and item["or_id"] not in known_rooms:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] names unknown OR {item['or_id']!r}")
            elif kind == "reschedule_surgery":
                if not isinstance(item.get("booking_id"), str) or not item["booking_id"] or not isinstance(item.get("target"), dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] reschedule_surgery requires booking_id and target")
                target = item["target"]
                try:
                    if target.get("domain") != "OR" or not target.get("resource_id"):
                        raise ValueError()
                    datetime.fromisoformat(target["start"])
                except (KeyError, TypeError, ValueError):
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] target requires domain OR, resource_id and ISO start") from None
                if target["resource_id"] not in {r["or_id"] for r in self.twin.t["operating_rooms"]}:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] names unknown OR {target['resource_id']!r}")
                if item["booking_id"] not in {r["surgery_id"] for r in self.twin.t["surgeries"]}:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] names unknown surgery {item['booking_id']!r}")
            else:
                raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] has unsupported type {kind!r}")
            normalized.append(item)
        db = getattr(self.twin.t, "path", None)
        stat = db.stat() if db is not None and db.exists() else None
        data_version = body.get("data_version") or (f"sqlite:{stat.st_size}:{stat.st_mtime_ns}" if stat else "csv-snapshot-v1")
        return Scenario(unit, mult, body.get("as_of"), horizon, tuple(normalized),
                        str(data_version), str(body.get("policy_version") or self.policy_fingerprint()),
                        seed, str(body.get("created_by", "")))

    def policy_fingerprint(self) -> str:
        """Changes whenever any structured policy file is added, edited or removed."""
        h = hashlib.sha256()
        for p in sorted(self.policy_dir.glob("*.md")):
            h.update(p.name.encode() + b"\0" + p.read_bytes() + b"\0")
        return h.hexdigest()

    def retriever(self):
        structured = FolderPolicyRetriever(self.policy_dir, extra=self.twin.policy_docs())
        return CompositeRetriever(structured, self.corpus) if self.corpus else structured

    def _orchestrator(self, language: str, audit, use_llm: bool = False) -> Orchestrator:
        """The LLM wording is used only when a user explicitly creates a decision. Dashboard refreshes, alerts
        and previews always use the deterministic template, so they never spend API quota."""
        return Orchestrator(Settings(language=language if language in ("ar", "en") else "ar"), retriever=self.retriever(),
                            explainer=llm.explainer() if use_llm else TemplateExplainer(), audit=audit)

    def _inputs(self, as_of: datetime, scenario: Scenario):
        return self.twin.inputs(as_of, scenario, [a for _, a in self.applied])

    # ───────────── read-only pages ─────────────
    def meta(self) -> dict:
        return {"first_day": self.twin.first_day, "last_day": self.twin.last_day, "default_as_of": self.twin.default_as_of.isoformat(),
                "units": list(BED_UNITS), "synthetic": True}

    def overview(self, q): return insights.overview(self.twin, self.parse_as_of(q.get("as_of", [None])[0]))
    def capacity(self, q): return insights.capacity(self.twin, self.parse_as_of(q.get("as_of", [None])[0]))
    def staff(self, q): return insights.staff(self.twin, self.parse_as_of(q.get("as_of", [None])[0]))
    def operating_rooms(self, q): return insights.operating_rooms(self.twin, self.parse_as_of(q.get("as_of", [None])[0]))
    def forecasts(self, q): return insights.forecasts(self.twin, self.parse_as_of(q.get("as_of", [None])[0]))

    def quality(self) -> dict:
        return insights.quality(self.twin, ROOT / "validation_report.json")

    def nurse_policy_units(self) -> set[str]:
        return {d.unit for d in FolderPolicyRetriever(self.policy_dir).docs if d.key == "nurse.max_patients_per_nurse"}

    def _alerts_for(self, as_of: datetime) -> dict:
        """Baseline agents run + alerts, cached per (moment, sandbox revision, policy revision). No LLM involved."""
        key = (as_of.isoformat(), self.store.revision, self.policy_fingerprint())
        with self.lock:
            if key not in self._alert_cache:
                decision = asyncio.run(self._orchestrator("en", InMemoryAudit()).run(self._inputs(as_of, Scenario())))
                items = insights.build_alerts(self.twin, as_of, decision, self.nurse_policy_units(), self.quality(), llm.config()["configured"])
                text = lambda a: (f"{a.pool.replace(':', ' ')} {a.delta:+d}" if isinstance(a, PoolAdjustment) else
                                  f"move {a.booking_id} to {a.to_slot.resource_id} on {a.to_slot.start:%d %b}" if isinstance(a, Reschedule) else "alert")
                self._alert_cache.clear() if len(self._alert_cache) > 32 else None
                self._alert_cache[key] = {
                    "as_of": as_of.isoformat(), "alerts": items, "needs_attention": sum(a["severity"] != "info" for a in items),
                    "unmet": dict(decision.card.unmet), "baseline": {"accepted": len(decision.accepted), "rejected": len(decision.rejected), "bottleneck": decision.card.critical_bottleneck},
                    "recommendations": [{"agent": p.agent, "summary": "; ".join(text(a) for a in p.actions),
                                         "summary_ar": "; ".join(render(describe(a), "ar") for a in p.actions),
                                         "actions": to_jsonable(p.actions), "rationale": list(p.rationale),
                                         "rationale_ar": [render(x, "ar") for x in p.rationale],
                                         "impact_basis": "simulated" if p.impact is not None else "assumed" if p.effects else "none"} for p in decision.accepted],
                    "rejected": [{"agent": r.proposal.agent, "reasons": list(r.reasons), "reasons_ar": [render(x, "ar") for x in r.reasons],
                                  "reason_codes": [c for m in r.reasons for c in codes(m)]} for r in decision.rejected]}
            return self._alert_cache[key]

    def alerts(self, q: dict) -> dict:
        return self._alerts_for(self.parse_as_of(q.get("as_of", [None])[0]))

    def twin_map(self, q): return insights.twin_map(self.twin, self.parse_as_of(q.get("as_of", [None])[0]))

    def health(self) -> dict:
        return {"ok": True, "time": datetime.now(timezone.utc).isoformat(), "data": {"from": self.twin.first_day, "to": self.twin.last_day},
                "llm": {"configured": llm.config()["configured"]}, "sandbox_revision": self.store.revision,
                "pending": sum(1 for r in self.store.records.values() if r["status"] == "PENDING"), "synthetic": True}

    def llm_test(self, principal: Principal | None = None) -> dict:
        """A real connection check against the provider. Reads .env again first so a freshly added key works."""
        self._need(principal, "run")
        llm.load_env(ROOT / ".env")
        result = llm.client.test()
        self.log(principal.username, "llm.test", ok=result["ok"], category=result["category"])
        return result

    # ───────────── assistant ─────────────
    def assistant_ask(self, body: dict, principal: Principal | None = None) -> dict:
        p = self._need(principal, "read")
        message = str(body.get("message", "")).strip()
        if not message:
            raise ApiError(HTTPStatus.BAD_REQUEST, "message is required")
        as_of = self.parse_as_of(body.get("as_of"))
        with self.lock:
            out = self.assistant.ask(p.username, message, as_of, str(body.get("language", "ar")))
        self.log(p.username, "assistant.ask", intent=out["intent"], mode=out["mode"], notes=out["notes"])
        return out

    def assistant_history(self, principal: Principal | None = None) -> dict:
        p = self._need(principal, "read")
        return {"history": self.assistant.history(p.username), "mode": "llm" if llm.config()["configured"] else "local"}

    def assistant_reset(self, principal: Principal | None = None) -> dict:
        self.assistant.reset(self._need(principal, "read").username)
        return {"ok": True}

    def status(self) -> dict:
        q = self.quality()
        return {
            "llm": llm.status(),
            "features": [
                {"name": "Executive summary wording", "available": llm.config()["configured"],
                 "note": "LLM wording, accepted only if every sentence is supported by the evidence." if llm.config()["configured"] else "Needs GROQ_API_KEY. The deterministic template is used meanwhile."},
                {"name": "AI assistant: local answers", "available": True, "note": "Answers from the backend data by intent, with sources. Works without a key."},
                {"name": "AI assistant: LLM-assisted answers", "available": llm.config()["configured"], "note": "Re-words the same evidence; rejected if unsupported." if llm.config()["configured"] else "Needs GROQ_API_KEY."},
                {"name": "Natural-language what-if questions", "available": False, "note": "Not implemented. Scenarios are set with the controls."},
                {"name": "Simulation engine (waiting time, queues)", "available": False, "note": "No engine is connected; the pack's stored results are shown as reference only."},
                {"name": "Source search (BM25, Arabic and English)", "available": True, "note": "Runs locally on the corpus and the pack policies."},
                {"name": "Constraint checking and arbitration", "available": True, "note": "Deterministic; runs locally."}],
            "persistence": {"decisions": len(self.store.records), "applied_in_sandbox": len(self.applied), "sandbox_revision": self.store.revision, "repairs": self.store.repairs,
                            "audit_events": len(self.audit_tail(10_000)), "runtime_dir": str(self.runtime)},
            "corpus": getattr(self.corpus, "stats", None), "data": {"period": q["period"], "days": q["days"], "tables": q["tables"]},
            "quality": q["summary"], "generated_at": datetime.now(timezone.utc).isoformat()}

    def knowledge(self, q: dict) -> dict:
        query = (q.get("q", [""])[0] or "").strip()[:200]
        r = self.retriever()
        passages = asyncio.run(r.search(query, 8)) if query else []
        kind = lambda p: "policy value" if p.doc_id.startswith("dashboard-") else ("pack policy" if p.doc_id.startswith("POL-") else "corpus")
        sources = [{"id": s["id"], "title": s["title"], "version": s.get("version"), "country": s.get("country"),
                    "status": s.get("status"), "license": s.get("license_note") or s.get("license") or s.get("reuse") or None}
                   for s in (self.corpus.sources.values() if self.corpus else [])]
        values = [{"unit": d.unit, "key": d.key, "value": d.value, "source": d.source}
                  for d in FolderPolicyRetriever(self.policy_dir).docs if d.key and d.approved]
        return {"query": query, "passages": [{"id": p.doc_id, "source": p.source, "text": p.text[:600], "score": p.score, "kind": kind(p)} for p in passages],
                "sources": sources, "corpus": getattr(self.corpus, "stats", None), "policy_values": values,
                "pack_policies": [{"id": d.id, "source": d.source, "text": d.text} for d in self.twin.policy_docs()]}

    # ───────────── what-if ─────────────
    def simulate(self, body: dict, principal: Principal | None = None) -> dict:
        """Preview a scenario: run the agents on it, apply the accepted actions to a copy of the twin and
        report capacity arithmetic before/after. Nothing is stored. No queue/wait simulation exists."""
        if principal and not body.get("created_by"):
            body = {**body, "created_by": principal.username}
        as_of, scenario = self.parse_as_of(body.get("as_of")), self.parse_scenario(body)
        from dataclasses import replace
        scenario = replace(scenario, as_of=as_of.isoformat())
        for i, item in enumerate(scenario.interventions):
            if item["type"] == "reschedule_surgery":
                target_start = datetime.fromisoformat(item["target"]["start"])
                if target_start <= as_of:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] target must be after as_of")
                if (target_start - as_of).days > scenario.horizon:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] target must fall within the scenario horizon")
                if self.twin.snapshot(as_of).booking(item["booking_id"]) is None:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] surgery is not a movable booking at as_of")
            elif item["type"] == "or_closed":
                for day in item["dates"]:
                    closed = datetime.fromisoformat(day)
                    if closed.date() < as_of.date() or (closed.date() - as_of.date()).days >= scenario.horizon:
                        raise ApiError(HTTPStatus.BAD_REQUEST, f"interventions[{i}] closure date must fall within as_of and the scenario horizon")
        with self.lock:
            inputs = self._inputs(as_of, scenario)
            decision = asyncio.run(self._orchestrator(body.get("language", "en"), InMemoryAudit()).run(inputs))
            actions = [a for p in decision.accepted for a in p.actions]
            after = apply_actions(inputs.twin, actions)
        f = inputs.forecast
        lang = body.get("language") if body.get("language") in ("ar", "en") else "en"
        relief = {}                                      # pool -> demand relief that rests on an ASSUMPTION
        for p in decision.accepted:
            for e in p.effects:
                relief[e.pool] = relief.get(e.pool, 0.0) + e.beds

        def state(snap):
            rows = {}
            for unit in BED_UNITS:
                pool = snap.pools[f"{unit}:beds"]
                peak = f.peak(f"{unit}:beds:demand", "upper")
                short = None if peak is None else max(0, math.ceil(peak - 1e-9) - pool.total)
                assumed = relief.get(pool.key, 0.0)
                rows[unit] = {"beds": pool.total, "occupied_now": pool.committed, "peak_demand_beds": None if peak is None else round(peak, 1),
                              "peak_utilisation_pct": None if peak is None or not pool.total else round(100 * peak / pool.total, 1),
                              # confirmed: counts only beds that really move; never reduced by assumed relief
                              "shortfall_beds": short,
                              "assumed_relief_beds": assumed or None,
                              "shortfall_if_assumed_beds": None if short is None or not assumed else max(0, math.ceil(short - assumed - 1e-9))}
            return rows

        rates = {r["cost_category"]: float(r["rate_egp"]) for r in self.twin.t["cost_rates"]}
        day_rate = {"ICU": rates.get("ICU_BED_DAY"), "WARD": rates.get("BED_DAY")}
        b, a = state(inputs.twin), state(after)
        moved = {u: a[u]["beds"] - b[u]["beds"] for u in BED_UNITS}
        cost = None
        if all(day_rate.get(u) is not None for u in ("ICU", "WARD")):
            cost = round(sum(moved[u] * day_rate[u] for u in ("ICU", "WARD")), 0)
        # Only OR moves represent postponed procedures; clinic appointment moves
        # do not imply ICU bed relief or a postponed surgery.
        rescheduled = [x for p in decision.accepted for x in p.actions
                       if hasattr(x, "booking_id") and x.from_slot.domain == "OR"]
        view = decision.to_dict()
        texts = decision_texts(decision, lang)
        view = overlay(view, texts, lang)
        n_post, total_relief = len(rescheduled), round(sum(relief.values()), 2)
        unavailable = [
            {"metric_key": "waiting", "metric": Msg("sim.m_wait").render(lang), "reason": Msg("sim.na_wait").render(lang)},
            {"metric_key": "revenue", "metric": Msg("sim.m_revenue").render(lang), "reason": Msg("sim.na_revenue").render(lang)},
            {"metric_key": "overtime", "metric": Msg("sim.m_overtime").render(lang), "reason": Msg("sim.na_overtime").render(lang)}]
        if n_post:
            unavailable.insert(0, {"metric_key": "effect", "metric": Msg("sim.m_relief").render(lang),
                                   "reason": Msg("sim.na_relief", n=n_post, relief=total_relief).render(lang)})
        result = {
            "as_of": as_of.isoformat(), "scenario": to_jsonable(scenario), "before": b, "after": a, "bed_change": moved,
            "capacity_cost_change_egp_per_day": cost,
            "cost_note": Msg("sim.cost_note").render(lang),
            # What the cost figure is made of, so it can be checked: moved beds x daily rate. Not a simulation.
            "cost_basis": {"kind": "rate_arithmetic", "simulated": False, "daily_rates_egp": {u: day_rate[u] for u in ("ICU", "WARD")},
                           "beds_moved": {u: moved[u] for u in ("ICU", "WARD")}, "excludes": ["postponed procedures", "staffing cost"]},
            "rescheduled_bookings": n_post,
            "assumed_relief_beds": relief or None,
            "impact_basis": {"capacity_changes": "computed", "postponements": "assumed" if n_post else None},
            "unavailable": unavailable,
            "pack_reference": [{"id": r["simulation_id"], "name": r["scenario_name"], "results": json.loads(r["results_json"])}
                               for r in self.twin.t["simulation_runs"]],
            "decision": {"accepted": view["accepted"], "rejected": view["rejected"], "card": view["card"], "reports": view["reports"]}}
        result["core"] = self._scenario_core(as_of, scenario, inputs.twin)
        self._persist_simulation(scenario, result, as_of)
        return result

    def _scenario_core(self, as_of, scenario, initial_snapshot):
        """Deterministic, isolated scenario arithmetic. Unvalidated baselines stay labeled as assumptions."""
        from dataclasses import replace
        from hospital_agents.forecasting import _targets, _weekday_mean

        targets = _targets(self.twin)
        def weekday_values(key):
            values = targets.get(key, {}).get("values", {})
            history = sorted((day, value) for day, value in values.items() if day < as_of.date())
            return [_weekday_mean(history, as_of.date() + timedelta(days=offset))
                    for offset in range(1, scenario.horizon + 1)]
        snap = replace(initial_snapshot, pools=dict(initial_snapshot.pools), slots=tuple(initial_snapshot.slots),
                       bookings=tuple(initial_snapshot.bookings))
        notes, rejected, accepted_moves = [], [], []
        multipliers = {u: (scenario.demand_multiplier if u == scenario.unit else 1.0)
                       for u in BED_UNITS}
        arrivals_multiplier = 1.0
        staff_delta = {}
        # Keep modifications local to this immutable snapshot.
        pools = dict(snap.pools)
        slots = list(snap.slots)
        for item in scenario.interventions:
            kind = item["type"]
            if kind == "demand_change":
                multipliers[item["unit"]] *= float(item["x"])
            elif kind == "er_arrivals_surge":
                arrivals_multiplier *= float(item["x"])
            elif kind == "staff_change":
                key = f'{item["unit"]}:{"nurses" if item["role"] == "NURSE" else "doctors"}'
                pool = pools.get(key)
                if pool is None:
                    rejected.append({"intervention": item, "reason": f"staff pool {key} is unavailable"})
                    continue
                before = pool.total
                delta = item.get("delta")
                if delta is None:
                    delta = -math.floor(before * float(item["absent_pct"]) / 100)
                if before + delta < 0:
                    rejected.append({"intervention": item, "reason": f"requested staffing reduction exceeds rostered {key} coverage ({before})"})
                    continue
                if item["role"] == "NURSE" and delta:
                    proposal = Proposal(f"staff-{len(rejected)}", "scenario", "Nurse coverage change",
                                        (PoolAdjustment(key, int(delta)),), ())
                    policies = asyncio.run(self.retriever().values([item["unit"]], as_of))
                    gate = Arbitrator(Settings()).resolve(snap, policies, (proposal,))
                    if gate.rejected:
                        rejected.append({"intervention": item, "reason": "; ".join(gate.rejected[0].reasons)})
                        continue
                pools[key] = replace(pool, total=before + delta)
                staff_delta[key] = staff_delta.get(key, 0) + delta
            elif kind == "bed_change":
                key, delta = f'{item["unit"]}:beds', int(item["delta"])
                pool = pools.get(key)
                if pool is None or pool.total + delta < pool.committed:
                    rejected.append({"intervention": item, "reason": "bed change would fall below occupied beds or the bed pool is unavailable"})
                elif delta > 0:
                    notes.append({"intervention": item, "status": "assumed", "warning": "physical ceiling, staffed-bed authorization and equipment capacity are not verifiable from this data"})
                else:
                    pools[key] = replace(pool, total=pool.total + delta)
            elif kind == "or_closed":
                dates, room = set(item["dates"]), item.get("or_id")
                slots = [s for s in slots if not (s.key.domain == "OR" and s.key.start.date().isoformat() in dates and (room is None or s.key.resource_id == room))]
            elif kind == "reschedule_surgery":
                bid, target = item["booking_id"], item["target"]
                booking = snap.booking(bid)
                target_key = SlotKey("OR", target["resource_id"], datetime.fromisoformat(target["start"]))
                if booking is None:
                    rejected.append({"intervention": item, "reason": "booking_id is unknown at this as_of"})
                    continue
                proposal = Proposal(f"scenario-{len(accepted_moves)}", "scenario", "Requested surgery move",
                                    (Reschedule(bid, booking.slot, target_key),), ())
                test_snapshot = replace(snap, pools=pools, slots=tuple(slots))
                resolution = Arbitrator(Settings()).resolve(test_snapshot, PolicyBundle(), (proposal,))
                if resolution.rejected:
                    rejected.append({"intervention": item, "reason": "; ".join(resolution.rejected[0].reasons)})
                else:
                    accepted_moves.append((proposal, item))
                    # Subsequent proposals see this booking and occupancy change.
                    snap = apply_actions(test_snapshot, proposal.actions)
                    slots = list(snap.slots)
        snap = replace(snap, pools=pools, slots=tuple(slots))
        assumption = "assumption: unvalidated baseline forecast"
        demand = {}
        for unit in BED_UNITS:
            points = [value for value in weekday_values(f"{unit}:occupancy") if value is not None]
            pool = snap.pools.get(f"{unit}:beds")
            if not points or pool is None:
                demand[unit] = {"status": "abstain", "reason": "no weekday-mean baseline available"}
                continue
            scale = self.twin.beds_total.get(unit, 0) * multipliers[unit]
            peak = max(float(value) * scale for value in points)
            shortfall = max(0, math.ceil(peak - 1e-9) - pool.total)
            row = {"status": "assumption", "label": assumption, "baseline": round(peak / multipliers[unit], 2),
                   "demand": round(peak, 2), "beds": pool.total, "shortfall": shortfall,
                   "delta_shortfall": None}
            demand[unit] = row
        for unit in BED_UNITS:
            row = demand.get(unit)
            nurse = [value for value in weekday_values(f"{unit}:nurses") if value is not None]
            if row and row.get("status") == "assumption" and nurse:
                required = max(float(value) for value in nurse)
                current = snap.pools.get(f"{unit}:nurses")
                row["nurse_demand"] = {"status": "assumption", "label": assumption, "required": round(required, 2),
                                       "available": current.total if current else None,
                                       "shortfall": max(0, math.ceil(required - 1e-9) - current.total) if current else None}
            if row and row.get("status") == "assumption":
                row["delta_shortfall"] = row["shortfall"] - max(0, math.ceil(row["baseline"] - 1e-9) - initial_snapshot.pools[f"{unit}:beds"].total)
                donor_headroom = 0
                for donor in BED_UNITS:
                    if donor == unit or demand.get(donor, {}).get("status") != "assumption":
                        continue
                    donor_pool = snap.pools.get(f"{donor}:beds")
                    if donor_pool:
                        donor_headroom += max(0, donor_pool.total - math.ceil(demand[donor]["demand"] - 1e-9))
                row["donor_headroom_beds"] = donor_headroom
                row["why_nothing_moved"] = ("no shortfall under this baseline assumption" if not row["shortfall"] else
                                             "no sourced transfer policy or verified staffed-bed/equipment ceiling")
                row["what_would_help"] = ([f"verify transfer policy; up to {donor_headroom} donor beds appear unused in the baseline"]
                                           if row["shortfall"] and donor_headroom else
                                           ["verify staffed-bed and equipment ceiling from operational sources"]
                                           if row["shortfall"] else ["no capacity action indicated by this assumption"])
        arrivals = [value for value in weekday_values("er_arrivals") if value is not None]
        doctor_demand = {u: {"status": "abstain", "reason": "no doctor-demand baseline in the data pack"} for u in BED_UNITS}
        resources = {u: {"status": "abstain", "reason": "no resource-demand baseline in the data pack"} for u in BED_UNITS}
        return {"before_after_delta": {u: {"label": demand[u].get("label"),
                                                  "baseline_shortfall": (max(0, math.ceil(demand[u]["baseline"] - 1e-9) - initial_snapshot.pools[f"{u}:beds"].total) if demand[u].get("status") == "assumption" else None),
                                                  "scenario_shortfall": demand[u].get("shortfall"), "delta": demand[u].get("delta_shortfall")}
                                         for u in BED_UNITS},
                "bed_demand": demand, "staff_delta": staff_delta,
                "er_arrivals": {"status": "assumption", "label": assumption, "baseline_mean": round(sum(arrivals) / len(arrivals), 2) if arrivals else None,
                                "scenario_mean": round(sum(arrivals) / len(arrivals) * arrivals_multiplier, 2) if arrivals else None},
                "doctor_demand": doctor_demand, "resource_demand": resources,
                "reschedules_accepted": [x[1] for x in accepted_moves], "rejected": rejected, "notes": notes,
                "wait_revenue_overtime": {k: {"status": "unavailable", "reason": "no calibrated simulation inputs"} for k in ("wait", "revenue", "overtime")},
                "seed": scenario.seed}

    def _persist_simulation(self, scenario, result, as_of):
        db_path = getattr(self.twin.t, "path", None)
        if db_path is None:
            return
        sid, now = str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()
        params = to_jsonable(scenario)
        params["as_of"] = as_of.isoformat()
        result["simulation_id"] = sid
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("INSERT INTO simulation_runs (simulation_id,created_at,scenario_name,scenario_type,baseline_or_scenario,random_seed,start_time,end_time,status,parameters_json,results_json,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (sid, now, "what-if", "deterministic", "scenario", scenario.seed, as_of.isoformat(), as_of.isoformat(), "completed", json.dumps(params), json.dumps(result), "replayable scenario contract"))
            for i, (kind, details) in enumerate((("scenario", params), ("result", result.get("core", {})))):
                conn.execute("INSERT INTO simulation_events (simulation_event_id,simulation_id,event_time,entity_type,entity_id,event_type,details_json) VALUES (?,?,?,?,?,?,?)",
                             (f"{sid}-{i}", sid, now, "scenario", sid, kind, json.dumps(details)))
            conn.commit()

    def replay_simulation(self, simulation_id: str) -> dict:
        db_path = getattr(self.twin.t, "path", None)
        if db_path is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "stored simulations are unavailable for CSV fallback data")
        with closing(sqlite3.connect(db_path)) as conn:
            row = conn.execute("SELECT parameters_json FROM simulation_runs WHERE simulation_id=?", (simulation_id,)).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "unknown simulation")
        params = json.loads(row[0])
        return self.simulate(params)

    def save_scenario_draft(self, body: dict, principal: Principal | None = None) -> dict:
        actor = self._need(principal, "run")
        as_of = self.parse_as_of(body.get("as_of"))
        scenario = self.parse_scenario(body)
        from dataclasses import replace
        scenario = replace(scenario, as_of=as_of.isoformat(), created_by=actor.username)
        draft_id = str(uuid.uuid4())
        draft = {"id": draft_id, "status": "DRAFT", "created_at": datetime.now(timezone.utc).isoformat(),
                 "created_by": actor.username, "scenario": to_jsonable(scenario)}
        with self.lock:
            self.scenario_drafts[draft_id] = draft
            atomic_write(self.drafts_path, json.dumps(self.scenario_drafts, ensure_ascii=False, indent=2), private=True)
        self.log(actor.username, "scenario.draft_saved", scenario_id=draft_id, seed=scenario.seed)
        return draft

    def list_scenario_drafts(self, principal: Principal | None = None) -> list[dict]:
        actor = self._need(principal, "run")
        rows = self.scenario_drafts.values()
        if actor.role != "operations_manager":
            rows = (r for r in rows if r["created_by"] == actor.username)
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)

    # ───────────── decisions ─────────────
    def run(self, body: dict, principal: Principal | None = None) -> dict:
        """Run the agents and store the result as a PENDING decision."""
        as_of, scenario = self.parse_as_of(body.get("as_of")), self.parse_scenario(body)
        actor = f"{principal.username} ({principal.label})" if principal else "system"
        with self.lock:
            fp, rev, seq = self.policy_fingerprint(), self.store.revision, self.store.next_seq()
            context = f"{scenario.unit}x{scenario.demand_multiplier:g}|policy:{fp[:12]}|run:{seq}"
            decision = asyncio.run(self._orchestrator(body.get("language", "ar"), self.audit, use_llm=True).run(self._inputs(as_of, scenario), context))
            view = decision.to_dict()
            language = body.get("language") if body.get("language") in ("ar", "en") else "ar"
            key = (as_of.isoformat(), scenario.unit, scenario.demand_multiplier, rev, fp)
            for rec in self.store.records.values():       # an identical earlier pending run is replaced by this one
                if rec["status"] == "PENDING" and rec["key"] == list(key):
                    rec["status"] = "SUPERSEDED"
            # A decision with nothing to apply is closed on creation: it must never sit in the approval queue as PENDING.
            reason = no_action_reason(decision)
            status = "PENDING" if reason is None else "NO_ACTION"
            now = datetime.now(timezone.utc).isoformat()
            for item, code_list in zip(view["rejected"], reason_codes(decision)):
                item["reason_codes"] = code_list
            for item, prop in zip(view["accepted"], decision.accepted):
                item["impact_basis"] = ("simulated" if prop.impact is not None else
                                        "assumed" if prop.effects else "none")
            view.update(status=status, as_of=as_of.isoformat(), scenario=to_jsonable(scenario), sandbox_rev=rev, policy_fp=fp,
                        seq=seq, key=list(key), created_by=actor,
                        decided_by="system" if reason else None, decided_at=now if reason else None,
                        note=render(reason, language) if reason else None,
                        no_action_code=reason.code if reason else None, language=language,
                        texts=decision_texts(decision, language))
            self.store.records[decision.id] = view
            self.store.save()
            self.log(actor, "decision.created" if not reason else "decision.created_no_action", decision=decision.id, scenario=scenario,
                     accepted=len(view["accepted"]), status=status)
            return self.view(decision.id, language)

    def _record(self, decision_id: str) -> dict:
        rec = self.store.records.get(decision_id)
        if rec is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "unknown decision")
        return rec

    def _stale_reason(self, rec: dict, lang: str = "en") -> str | None:
        if rec["status"] != "PENDING":
            return None
        if rec["sandbox_rev"] != self.store.revision:
            return Msg("stale.sandbox").render(lang)
        if rec["policy_fp"] != self.policy_fingerprint():
            return Msg("stale.policy").render(lang)
        return None

    def view(self, decision_id: str, lang: str | None = None) -> dict:
        """The stored decision with its text in `lang` (default: the language it was created in)."""
        rec = self._record(decision_id)
        lang = lang if lang in ("ar", "en") else rec.get("language", "en")
        reason = self._stale_reason(rec, lang)
        texts = rec.get("texts") or {}
        out = overlay({k: v for k, v in rec.items() if k != "texts"}, texts, lang) if texts \
            else {k: v for k, v in rec.items() if k != "texts"}
        return {**out, "stale": reason is not None, "stale_reason": reason}

    def decisions(self, lang: str | None = None) -> list[dict]:
        out = []
        for rec in sorted(self.store.records.values(), key=lambda r: -r["seq"]):
            lg = lang if lang in ("ar", "en") else rec.get("language", "en")
            reason = self._stale_reason(rec, lg)
            texts = (rec.get("texts") or {}).get(lg) or {}
            out.append({"id": rec["id"], "status": rec["status"], "stale": reason is not None, "stale_reason": reason,
                        "created_at": rec["created_at"], "created_by": rec["created_by"], "decided_by": rec["decided_by"],
                        "decided_at": rec["decided_at"], "note": rec["note"], "as_of": rec["as_of"], "scenario": rec["scenario"],
                        "accepted": len(rec["accepted"]), "rejected": len(rec["rejected"]),
                        "no_action_code": rec.get("no_action_code"), "unmet": dict(rec["card"].get("unmet") or {}),
                        "bottleneck": rec["card"]["critical_bottleneck"], "summary": texts.get("summary") or rec["explanation"]["text"]})
        return out

    def _gate_refusal(self, rec: dict) -> str | None:
        """Recheck a persisted decision against current data and sourced policies before apply.

        A decision created by an older backend, or loaded from runtime, must not bypass
        hard constraints simply because its actions were once labelled 'accepted'.
        Never silently reinterpret invalid stored actions as safe.
        """
        try:
            as_of = self.parse_as_of(rec["as_of"])
            scenario = self.parse_scenario({"unit": rec["scenario"]["unit"],
                                            "multiplier": rec["scenario"]["demand_multiplier"]})
            snapshot = self._inputs(as_of, scenario).twin
            proposals = tuple(Proposal(
                str(item["id"]), str(item["agent"]), str(item.get("title", "")),
                tuple(action_from_dict(a) for a in item["actions"]),
                tuple(item.get("rationale", ()))
            ) for item in rec["accepted"])
            if not proposals or not any(isinstance(a, (PoolAdjustment, Reschedule))
                                        for p in proposals for a in p.actions):
                return "no actionable proposals"
            units = sorted({p.unit for p in snapshot.pools.values()})
            policies = asyncio.run(self.retriever().values(units, as_of))
            resolution = Arbitrator(Settings()).resolve(snapshot, policies, proposals)
            if len(resolution.accepted) != len(proposals):
                return "; ".join(str(reason) for r in resolution.rejected for reason in r.reasons) or "hard constraints failed"
            return None
        except Exception:
            # Fail closed. Never reveal parser or validation internals from a stored record.
            return "decision cannot be verified against current data and policies"

    def _decide(self, decision_id: str, principal, kind: str, note: str = "") -> dict:
        actor = self._need(principal, "decide")
        with self.lock:
            rec = self._record(decision_id)
            if rec["status"] == "NO_ACTION":
                raise ApiError(HTTPStatus.CONFLICT, "nothing to apply: this decision has no action and was closed automatically (NO_ACTION)")
            if rec["status"] != "PENDING":
                raise ApiError(HTTPStatus.CONFLICT, f"decision is already {rec['status']}")
            if kind == "approve":
                if (reason := self._stale_reason(rec)):
                    raise ApiError(HTTPStatus.CONFLICT, f"stale: {reason}; run the agents again")
                if (refusal := self._gate_refusal(rec)):
                    raise ApiError(HTTPStatus.CONFLICT, f"safety gate refused approval: {refusal}")
                actions = [a for p in rec["accepted"] for a in map(action_from_dict, p["actions"])]
                if not any(isinstance(a, (PoolAdjustment, Reschedule)) for a in actions):
                    raise ApiError(HTTPStatus.CONFLICT, "nothing to apply: this decision has no accepted action that changes the sandbox. Reject it to close it")
                self.applied.append((decision_id, actions))
                self.store.bump()
                rec["status"] = "APPLIED"
            else:
                rec["status"] = "REJECTED"
            rec.update(decided_by=f"{actor.username} ({actor.label})", decided_at=datetime.now(timezone.utc).isoformat(), note=note[:300] or None)
            self.store.save()
            self.log(actor.username, "decision.approved_and_applied_in_sandbox" if kind == "approve" else "decision.rejected",
                     decision=decision_id, role=actor.role, note=note[:300])
            return self.view(decision_id)

    def approve(self, decision_id: str, body: dict, principal: Principal | None = None) -> dict:
        return self._decide(decision_id, principal, "approve", str(body.get("note", "")))

    def reject(self, decision_id: str, body: dict, principal: Principal | None = None) -> dict:
        return self._decide(decision_id, principal, "reject", str(body.get("reason", "")))

    def rollback(self, body: dict, principal: Principal | None = None) -> dict:
        """Undo the most recently applied decision (last in, first out keeps the sandbox consistent)."""
        actor = self._need(principal, "decide")
        with self.lock:
            if not self.applied:
                raise ApiError(HTTPStatus.CONFLICT, "nothing to roll back")
            decision_id, actions = self.applied.pop()
            self.store.bump()
            rec = self.store.records.get(decision_id)
            if rec:
                rec.update(status="ROLLED_BACK", decided_by=f"{actor.username} ({actor.label})",
                           decided_at=datetime.now(timezone.utc).isoformat(), note=str(body.get("note", ""))[:300] or None)
            self.store.save()
            self.log(actor.username, "decision.rolled_back", decision=decision_id, role=actor.role, inverse=invert(actions))
            return self.view(decision_id) if rec else {"id": decision_id, "status": "ROLLED_BACK"}

    def sandbox(self) -> dict:
        return {"applied": [{"decision_id": d, "actions": to_jsonable(a)} for d, a in self.applied]}

    def audit_tail(self, n: int = 200) -> list:
        f = self.runtime / "audit.jsonl"
        lines = f.read_text(encoding="utf-8").splitlines()[-n:] if f.exists() else []
        return [json.loads(l) for l in reversed(lines)]

    # ───────────── policies ─────────────
    # A structured nurse-ratio policy entered by an Operations Manager. It is stored as a policy file whose
    # source says so; it is NOT an approved hospital policy and the dashboard labels it accordingly.
    def policies(self) -> dict:
        r = FolderPolicyRetriever(self.policy_dir)
        rows = [{"unit": d.unit, "value": d.value, "source": d.source, "approved": d.approved}
                for d in r.docs if d.key == "nurse.max_patients_per_nurse"]
        if not any(d.unit == "ER" and d.key == "nurse.max_patients_per_nurse" for d in r.docs):
            rows.append({"unit": "ER", "value": None, "source": "Unapproved template; requires a manager-entered value and approval", "approved": False})
        return {"nurse_ratio": rows, "fingerprint": self.policy_fingerprint()[:12]}

    def set_policy(self, body: dict, principal: Principal | None = None) -> dict:
        actor = self._need(principal, "policy")
        unit = body.get("unit")
        if unit not in BED_UNITS:
            raise ApiError(HTTPStatus.BAD_REQUEST, "unit must be ER, ICU or WARD")
        path = self.policy_dir / f"dashboard-nurse-ratio-{unit}.md"
        with self.lock:
            if body.get("approve") is True:
                if unit != "ER" or not path.exists():
                    raise ApiError(HTTPStatus.CONFLICT, "an ER nurse-ratio draft with a value is required before approval")
                from hospital_agents.policies import parse_policy
                current = parse_policy(path)
                if current.value is None:
                    raise ApiError(HTTPStatus.CONFLICT, "enter a positive ER nurse-ratio value before approval")
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                path.write_text(
                    f"---\nid: dashboard-nurse-ratio-ER\nsource: Entered and approved in the dashboard by {actor.username} ({actor.label}) at {stamp}; not a hospital clinical policy\n"
                    f"key: nurse.max_patients_per_nurse\nunit: ER\nvalue: {current.value:g}\napproved: true\n---\n"
                    "Manager-entered ER operational constraint. Not a clinical standard.\n", encoding="utf-8")
                self.log(actor.username, "policy.approved", role=actor.role, unit=unit, value=current.value)
            elif body.get("value") in (None, ""):
                path.unlink(missing_ok=True)
                self.log(actor.username, "policy.removed", role=actor.role, unit=unit)
            else:
                try:
                    value = float(body["value"])
                except (TypeError, ValueError):
                    value = math.nan
                if not (math.isfinite(value) and value > 0):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "value must be a positive number (max patients per nurse)")
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                approved = unit != "ER"
                source = (f"Entered in the dashboard by {actor.username} ({actor.label}) at {stamp} - NOT an approved hospital policy"
                          if unit != "ER" else f"Unapproved ER draft entered by {actor.username} ({actor.label}) at {stamp}")
                path.write_text(
                    f"---\nid: dashboard-nurse-ratio-{unit}\n"
                    f"source: {source}\nkey: nurse.max_patients_per_nurse\nunit: {unit}\nvalue: {value:g}\napproved: {str(approved).lower()}\n---\n"
                    f"Maximum patients per nurse for {unit}, as entered by {actor.username}.\n", encoding="utf-8")
                self.log(actor.username, "policy.draft_saved" if unit == "ER" else "policy.set", role=actor.role, unit=unit, value=value)
        return self.policies()


# ───────────────────────── HTTP layer ─────────────────────────

class Handler(BaseHTTPRequestHandler):
    app: App

    def _send(self, status: int, payload, ctype: str = "application/json") -> None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(data)

    def _static(self, rel: str) -> None:
        path = (STATIC / rel).resolve()
        if STATIC.resolve() not in path.parents or path.suffix not in CONTENT_TYPES or not path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "not found")
        self._send(200, path.read_bytes(), CONTENT_TYPES[path.suffix])

    def _principal(self) -> Principal | None:
        header = self.headers.get("Authorization", "")
        return self.app.auth.principal(header[7:] if header.startswith("Bearer ") else None)

    def _dispatch(self, method: str) -> None:
        url, a = urlparse(self.path), self.app
        parts = [p for p in url.path.split("/") if p]
        try:
            if method == "GET" and not parts:
                return self._send(200, (ROOT / "dashboard.html").read_bytes(), "text/html")
            if method == "GET" and parts[:1] == ["static"]:
                return self._static(unquote("/".join(parts[1:])))
            body = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > 100_000:
                    raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body too large")
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except json.JSONDecodeError:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "invalid JSON") from None
                if not isinstance(body, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "JSON object expected")
            if (method, parts) == ("POST", ["api", "login"]):
                try:
                    token, p = a.auth.login(str(body.get("username", "")), str(body.get("password", "")))
                except AuthError as e:
                    raise ApiError(HTTPStatus(e.status), e.message) from None
                a.log(p.username, "auth.login", role=p.role)
                return self._send(200, {"token": token, "user": self._user(p)})
            principal = self._principal()
            if principal is None:
                raise ApiError(HTTPStatus.UNAUTHORIZED, "sign in required")
            q = parse_qs(url.query)
            routes = {
                ("GET", "me"): lambda: self._user(principal), ("GET", "meta"): a.meta,
                ("GET", "overview"): lambda: a.overview(q), ("GET", "capacity"): lambda: a.capacity(q),
                ("GET", "staff"): lambda: a.staff(q), ("GET", "or"): lambda: a.operating_rooms(q),
                ("GET", "forecasts"): lambda: a.forecasts(q), ("GET", "alerts"): lambda: a.alerts(q),
                ("GET", "quality"): a.quality, ("GET", "status"): a.status, ("GET", "knowledge"): lambda: a.knowledge(q),
                ("GET", "health"): a.health, ("GET", "twin"): lambda: a.twin_map(q), ("GET", "assistant"): lambda: a.assistant_history(principal),
                ("POST", "assistant"): lambda: a.assistant_ask(body, principal), ("POST", "llm-test"): lambda: a.llm_test(principal),
                ("GET", "decisions"): lambda: a.decisions(q.get("lang", [None])[0]), ("GET", "sandbox"): a.sandbox, ("GET", "audit"): a.audit_tail,
                ("GET", "policies"): a.policies,
                ("GET", "scenario-drafts"): lambda: a.list_scenario_drafts(principal),
                ("POST", "simulate"): lambda: a.simulate(body, a._need(principal, "run")),
                ("POST", "run"): lambda: a.run(body, a._need(principal, "run")),
                ("POST", "policies"): lambda: a.set_policy(body, principal),
                ("POST", "scenario-drafts"): lambda: a.save_scenario_draft(body, principal),
                ("POST", "rollback"): lambda: a.rollback(body, principal),
                ("POST", "logout"): lambda: (a.auth.logout(self.headers.get("Authorization", "")[7:]), {"ok": True})[1],
            }
            if parts[:1] == ["api"] and len(parts) == 2 and (method, parts[1]) in routes:
                result = routes[(method, parts[1])]()
            elif (method, parts) == ("POST", ["api", "assistant", "reset"]):
                result = a.assistant_reset(principal)
            elif parts[:2] == ["api", "decisions"] and len(parts) == 3 and method == "GET":
                result = a.view(parts[2], q.get("lang", [None])[0])
            elif parts[:2] == ["api", "simulations"] and len(parts) == 4 and parts[3] == "replay" and method == "POST":
                a._need(principal, "run")
                result = a.replay_simulation(parts[2])
            elif method == "POST" and len(parts) == 4 and parts[:2] == ["api", "decisions"] and parts[3] in ("approve", "reject"):
                result = getattr(a, parts[3])(parts[2], body, principal)
            else:
                raise ApiError(HTTPStatus.NOT_FOUND, "not found")
            self._send(200, result)
        except ApiError as e:
            self._send(e.status, {"error": e.message})
        except Exception as e:                       # never leak a traceback to the browser
            self.log_error("unhandled: %r", e)
            self._send(500, {"error": "internal error"})

    @staticmethod
    def _user(p: Principal) -> dict:
        return {"username": p.username, "role": p.role, "role_label": p.label,
                "permissions": [k for k, roles in PERMISSIONS.items() if p.role in roles]}

    def do_GET(self): self._dispatch("GET")
    def do_POST(self): self._dispatch("POST")
    def log_message(self, fmt, *args): pass


def make_server(data_dir: Path, port: int = 8000, host: str = "127.0.0.1", *,
                runtime: Path = ROOT / "runtime", policy_dir: Path = ROOT / "policies") -> ThreadingHTTPServer:
    Handler.app = App(Path(data_dir), runtime, policy_dir)
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--reset-credentials", action="store_true", help="delete accounts and create new ones")
    args = ap.parse_args()
    loaded = llm.load_env(ROOT / ".env")                    # real environment variables always win over .env
    if args.reset_credentials:
        (ROOT / "runtime" / "users.json").unlink(missing_ok=True)
    if Path(args.data).resolve() == (ROOT / "data").resolve() and not (ROOT / "runtime" / "hdt.sqlite").exists():
        from db.build_db import build
        build(db_path=ROOT / "runtime" / "hdt.sqlite")
    server = make_server(Path(args.data), args.port)
    creds = Handler.app.auth.initial_credentials
    if creds:
        print("First run: accounts created (shown once; set HDT_MANAGER_PASSWORD etc. to choose your own):")
        for name, password in creds.items():
            print(f"  {name:<8} {password}")
    print(f"LLM: {'configured (' + llm.config()['model'] + ')' if llm.config()['configured'] else 'not configured, running without it (set GROQ_API_KEY in .env)'}")
    print(f"Dashboard: http://127.0.0.1:{args.port}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
