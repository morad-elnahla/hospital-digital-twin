"""HTTP API end to end with real sign-in: roles, lifecycle, staleness, persistence, validation."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import hospital_agents.auth as _auth  # noqa: E402

_auth.ITERATIONS = 2000   # tests only: keep sign-ins fast; production uses 200 000
_SHARED_TWIN = A.TwinData(ROOT / "data")  # immutable CSV snapshot shared; App/runtime state stays isolated

STRESS = {"unit": "ICU", "multiplier": 12, "language": "en"}
PASSWORDS = {"manager": "manager-pass-1", "analyst": "analyst-pass-1", "clinician": "clinician-pass-1", "viewer": "viewer-pass-1"}


class Api(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.start()
        for name, role in (("manager", "operations_manager"), ("analyst", "analyst"), ("clinician", "clinician"), ("viewer", "viewer")):
            self.app.auth.users.pop(name, None)
            self.app.auth.create_user(name, PASSWORDS[name], role)
        self.tokens = {}

    def start(self):
        with mock.patch.object(A, "TwinData", return_value=_SHARED_TWIN):
            self.srv = A.make_server(ROOT / "data", 0, runtime=self.tmp / "rt", policy_dir=self.tmp / "pol")
        self.app, self.port = A.Handler.app, self.srv.server_address[1]
        # Shrink the stdlib server's default 500ms shutdown poll interval; each test
        # owns a fresh server, so the default adds ~13 seconds across this file.
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.001}, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()

    def tearDown(self):
        self.stop()
        shutil.rmtree(self.tmp)

    def call(self, path, body=None, who=None, raw=None, headers=None):
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        h = dict(headers or {})
        if who:
            if who not in self.tokens:
                s, r = self.call("/api/login", {"username": who, "password": PASSWORDS[who]})
                self.tokens[who] = r["token"]
            h["Authorization"] = "Bearer " + self.tokens[who]
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method="GET" if data is None else "POST", headers=h)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def set_policies(self):
        for u in ("ICU", "WARD"):
            self.assertEqual(self.call("/api/policies", {"unit": u, "value": 40}, "manager")[0], 200)

    # ── authentication / authorization ──
    def test_everything_but_login_needs_a_session(self):
        for path in ("/api/meta", "/api/overview", "/api/decisions", "/api/audit", "/api/status"):
            self.assertEqual(self.call(path)[0], 401, path)
        self.assertEqual(self.call("/api/run", STRESS)[0], 401)
        self.assertEqual(self.call("/api/meta", headers={"Authorization": "Bearer forged"})[0], 401)

    def test_role_in_the_request_body_is_ignored(self):
        self.set_policies()
        _, d = self.call("/api/run", STRESS, "analyst")
        s, e = self.call(f"/api/decisions/{d['id']}/approve", {"role": "Operations Manager"}, "analyst")
        self.assertEqual(s, 403)
        self.assertEqual(self.call(f"/api/decisions/{d['id']}/approve", {"role": "operations_manager"}, "viewer")[0], 403)

    def test_clinician_can_preview_and_save_drafts_but_cannot_approve(self):
        self.assertEqual(self.call("/api/simulate", {"unit": "ICU", "multiplier": 1.3}, "clinician")[0], 200)
        status, draft = self.call("/api/scenario-drafts", {"unit": "ICU", "multiplier": 1.3, "seed": 7}, "clinician")
        self.assertEqual((status, draft["status"], draft["created_by"], draft["scenario"]["seed"]),
                         (200, "DRAFT", "clinician", 7))
        self.assertEqual(self.call("/api/scenario-drafts", who="clinician")[1][0]["id"], draft["id"])
        _, decision = self.call("/api/run", STRESS, "analyst")
        self.assertEqual(self.call(f"/api/decisions/{decision['id']}/approve", {}, "clinician")[0], 403)

    def test_er_nurse_ratio_requires_manager_entry_then_explicit_approval(self):
        row = next(x for x in self.call("/api/policies", who="viewer")[1]["nurse_ratio"] if x["unit"] == "ER")
        self.assertEqual((row["value"], row["approved"]), (None, False))
        self.assertEqual(self.call("/api/policies", {"unit": "ER", "value": 5}, "manager")[0], 200)
        row = next(x for x in self.call("/api/policies", who="viewer")[1]["nurse_ratio"] if x["unit"] == "ER")
        self.assertEqual((row["value"], row["approved"]), (5.0, False))
        self.assertEqual(self.call("/api/policies", {"unit": "ER", "value": 5}, "clinician")[0], 403)
        self.assertEqual(self.call("/api/policies", {"unit": "ER", "approve": True}, "manager")[0], 200)
        row = next(x for x in self.call("/api/policies", who="viewer")[1]["nurse_ratio"] if x["unit"] == "ER")
        self.assertEqual((row["value"], row["approved"]), (5.0, True))
        self.assertEqual(self.call("/api/policies", {"unit": "ICU", "value": 3, "role": "Operations Manager"}, "analyst")[0], 403)
        self.assertEqual(self.call("/api/rollback", {"role": "Operations Manager"}, "viewer")[0], 403)
        self.assertEqual(self.call("/api/run", STRESS, "viewer")[0], 403)

    def test_wrong_password_and_lockout(self):
        self.assertEqual(self.call("/api/login", {"username": "manager", "password": "nope"})[0], 401)
        for _ in range(5):
            self.call("/api/login", {"username": "viewer", "password": "bad"})
        self.assertEqual(self.call("/api/login", {"username": "viewer", "password": PASSWORDS["viewer"]})[0], 429)

    def test_logout_ends_the_session(self):
        self.assertEqual(self.call("/api/meta", who="viewer")[0], 200)
        self.call("/api/logout", {}, "viewer")
        self.assertEqual(self.call("/api/meta", headers={"Authorization": "Bearer " + self.tokens["viewer"]})[0], 401)

    # ── lifecycle ──
    def test_full_decision_lifecycle(self):
        self.set_policies()
        d = self.call("/api/run", {**STRESS, "multiplier": 12}, "analyst")[1]
        self.assertEqual((d["status"], d["accepted"], d["card"]["recommended_actions"]), ("ESCALATE", [], []))
        self.assertEqual(d["no_action_code"], "manager_escalation")
        self.assertIn("Unresolved shortfall 101 beds", d["note"])
        self.assertNotIn("no forecast shortfall", d["note"])
        self.assertTrue(d["scenario_core"]["bed_demand"]["ICU"]["residual_message"])
        self.assertNotIn({"code": "manager_escalation", "params": {"beds": 101}}, d["scenario_core"]["bed_demand"]["ICU"]["what_would_help"])
        code, refusal = self.call(f"/api/decisions/{d['id']}/approve", {}, "manager")
        self.assertEqual(code, 409)
        self.assertIn("ESCALATE", refusal["error"])
        self.assertEqual(self.call("/api/sandbox", who="viewer")[1]["applied"], [])
        code, ack = self.call(f"/api/decisions/{d['id']}/acknowledge-escalation", {"note": "Escalated to bed manager"}, "manager")
        self.assertEqual((code, ack["status"], ack["escalation_note"]), (200, "ESCALATE", "Escalated to bed manager"))
        actions = [e["action"] for e in self.call("/api/audit", who="viewer")[1]]
        self.assertIn("decision.created_escalation", actions)
        self.assertIn("decision.escalation_acknowledged", actions)

    def test_escalation_decisions_survive_a_restart_and_cannot_be_applied(self):
        self.set_policies()
        _, d = self.call("/api/run", STRESS, "analyst")
        self.assertEqual(d["status"], "ESCALATE")
        self.stop()
        self.start()
        self.tokens.clear()
        listed = {x["id"]: x for x in self.call("/api/decisions", who="viewer")[1]}
        self.assertEqual(listed[d["id"]]["status"], "ESCALATE")
        self.assertEqual(self.call(f"/api/decisions/{d['id']}/approve", {}, "manager")[0], 409)
        self.assertEqual(self.call("/api/sandbox", who="viewer")[1]["applied"], [])

    def test_scenario_run_without_relevant_actions_closes_as_no_action(self):
        self.set_policies()
        _, d = self.call("/api/run", STRESS, "analyst")
        self.assertEqual(d["status"], "ESCALATE")
        self.assertEqual(d["accepted"], [])
        self.assertEqual(self.call(f"/api/decisions/{d['id']}/approve", {}, "manager")[0], 409)

    def test_escalation_decisions_remain_closed_after_policy_changes(self):
        self.set_policies()
        _, first = self.call("/api/run", STRESS, "analyst")
        _, other = self.call("/api/run", {**STRESS, "as_of": "2026-10-16T08:00"}, "analyst")
        self.assertNotEqual(first["id"], other["id"])
        self.assertEqual((first["status"], other["status"]), ("ESCALATE", "ESCALATE"))
        self.assertEqual(self.call(f"/api/decisions/{other['id']}/approve", {}, "manager")[0], 409)
        self.assertEqual(self.call(f"/api/decisions/{first['id']}/approve", {}, "manager")[0], 409)
        _, third = self.call("/api/run", STRESS, "analyst")
        self.call("/api/policies", {"unit": "ICU", "value": 39}, "manager")
        self.assertEqual(third["status"], "ESCALATE")
        self.assertEqual(self.call(f"/api/decisions/{third['id']}/approve", {}, "manager")[0], 409)
        self.assertFalse(self.call(f"/api/decisions/{third['id']}", who="viewer")[1]["stale"])

    def test_every_run_gets_its_own_id_and_identical_pending_runs_are_superseded(self):
        self.set_policies()
        _, a = self.call("/api/run", STRESS, "analyst")
        _, b = self.call("/api/run", STRESS, "analyst")
        self.assertNotEqual(a["id"], b["id"])
        statuses = {x["id"]: x["status"] for x in self.call("/api/decisions", who="viewer")[1]}
        self.assertEqual((statuses[a["id"]], statuses[b["id"]]), ("ESCALATE", "ESCALATE"))
        self.assertEqual(self.call(f"/api/decisions/{a['id']}/approve", {}, "manager")[0], 409)

    def test_reject_records_reason_and_blocks_apply(self):
        self.set_policies()
        _, d = self.call("/api/run", STRESS, "analyst")
        self.assertEqual(d["status"], "ESCALATE")
        self.assertEqual(self.call(f"/api/decisions/{d['id']}/reject", {"reason": "not now"}, "manager")[0], 409)
        self.assertEqual(self.call(f"/api/decisions/{d['id']}/approve", {}, "manager")[0], 409)

    # ── simulation preview ──
    def test_simulation_preview_is_computed_without_creating_a_decision(self):
        self.set_policies()
        s, sim = self.call("/api/simulate", STRESS, "analyst")
        self.assertEqual(s, 200)
        self.assertEqual((sim["status"], sim["decision"]["status"]), ("ESCALATE", "ESCALATE"))
        self.assertEqual(sim["bed_change"], {"ER": 0, "ICU": 0, "WARD": 0})
        self.assertEqual(sim["before"]["ICU"]["shortfall_beds"], sim["after"]["ICU"]["shortfall_beds"])
        self.assertEqual(sim["capacity_cost_change_egp_per_day"], 0)
        self.assertTrue({"Waiting time change", "Revenue at risk change", "Overtime change"}.issubset(
            {u["metric"] for u in sim["unavailable"]}))
        self.assertEqual(self.call("/api/decisions", who="viewer")[1], [])

    # ── pages return real data ──
    def test_pages(self):
        for path, key in (("/api/overview", "cards"), ("/api/capacity", "units"), ("/api/staff", "on_shift_now"),
                          ("/api/or", "by_room"), ("/api/forecasts", "series"), ("/api/quality", "checks"),
                          ("/api/alerts", "alerts"), ("/api/twin", "departments"), ("/api/health", "ok"), ("/api/status", "features"), ("/api/knowledge?q=escalation", "passages")):
            s, body = self.call(path, who="viewer")
            self.assertEqual(s, 200, path)
            self.assertIn(key, body, path)
        self.assertTrue(self.call("/api/knowledge?q=escalation", who="viewer")[1]["passages"])

    def test_alerts_report_the_missing_policy_then_clear_it(self):
        ids = lambda: {a["id"] for a in self.call("/api/alerts", who="viewer")[1]["alerts"]}
        self.assertIn("policy-missing", ids())
        for u in ("ER", "ICU", "WARD"):
            self.call("/api/policies", {"unit": u, "value": 6}, "manager")
        self.call("/api/policies", {"unit": "ER", "approve": True}, "manager")
        self.assertNotIn("policy-missing", ids())

    # ── decision rules from the review ──
    def test_a_decision_without_actions_can_never_be_applied(self):
        _, d = self.call("/api/run", {**STRESS, "multiplier": 1, "as_of": "2026-10-20T08:00"}, "analyst")
        self.assertEqual(d["accepted"], [])
        s, err = self.call(f"/api/decisions/{d['id']}/approve", {}, "manager")
        self.assertEqual(s, 409)
        self.assertIn("nothing to apply", err["error"])
        self.assertEqual(self.call("/api/sandbox", who="viewer")[1]["applied"], [])
        # It is closed on creation (NO_ACTION), so it never waits in the approval queue and cannot be re-decided.
        self.assertEqual(d["status"], "NO_ACTION")
        self.assertEqual(self.call(f"/api/decisions/{d['id']}/reject", {"reason": "nothing to do"}, "manager")[0], 409)
        self.assertEqual(self.call(f"/api/decisions/{d['id']}", who="viewer")[1]["status"], "NO_ACTION")

    def test_icu_run_filters_clinic_suggestions_at_every_multiplier(self):
        for multiplier, expected_residual in ((12, 101), (1.3, 1)):
            _, d = self.call("/api/run", {"unit": "ICU", "multiplier": multiplier, "language": "en"}, "analyst")
            self.assertEqual(d["status"], "ESCALATE")
            self.assertEqual(d["scenario_core"]["bed_demand"]["ICU"]["residual_shortfall_beds"], expected_residual)
            self.assertEqual(d["accepted"], [])
            self.assertEqual(d["card"]["recommended_actions"], [])
            self.assertFalse(any(p["agent"] == "appointment" and p["proposals"] for p in d["reports"]))
            self.assertGreater(len(d["unrelated_suggestions"]), 0)
            # Suggestions are response-only and cannot be recovered from the stored decision.
            stored = self.call(f"/api/decisions/{d['id']}", who="viewer")[1]
            self.assertNotIn("unrelated_suggestions", stored)
            self.assertEqual(self.call(f"/api/decisions/{d['id']}/approve", {}, "manager")[0], 409)
            self.assertEqual(self.call(f"/api/decisions/{d['id']}/acknowledge-escalation", {"note": ""}, "manager")[0], 400)
            self.assertEqual(self.call("/api/sandbox", who="viewer")[1]["applied"], [])

    def test_no_action_decisions_never_enter_the_sandbox_revision_queue(self):
        self.set_policies()
        _, a = self.call("/api/run", STRESS, "analyst")
        _, pending = self.call("/api/run", {**STRESS, "multiplier": 11.9}, "analyst")
        self.assertEqual((a["status"], pending["status"]), ("ESCALATE", "ESCALATE"))
        self.assertFalse(self.call(f"/api/decisions/{pending['id']}", who="viewer")[1]["stale"])
        self.assertEqual(self.call(f"/api/decisions/{pending['id']}/approve", {}, "manager")[0], 409)

    # ── LLM safety on the dashboard ──
    def test_refreshing_the_dashboard_never_calls_the_llm(self):
        boom = mock.Mock(side_effect=AssertionError("LLM called during a dashboard refresh"))
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "secret-key-123"}), mock.patch("hospital_agents.llm.client.chat", boom):
            for path in ("/api/overview", "/api/alerts", "/api/capacity", "/api/staff", "/api/or", "/api/forecasts", "/api/twin", "/api/status", "/api/health", "/api/decisions", "/api/quality"):
                self.assertEqual(self.call(path, who="viewer")[0], 200, path)
            self.assertEqual(self.call("/api/simulate", STRESS, "analyst")[0], 200)
        boom.assert_not_called()

    def test_the_api_key_never_appears_in_any_response_or_log(self):
        # Avoid provider retry/backoff: this test checks key redaction, not network behavior.
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "secret-key-123", "GROQ_BASE_URL": "http://127.0.0.1:1/v1"}), \
             mock.patch("hospital_agents.llm.client.chat", side_effect=A.llm.LLMError("network")):
            self.call("/api/llm-test", {}, "analyst")
            self.call("/api/assistant", {"message": "how is the ICU?"}, "viewer")
            self.call("/api/run", STRESS, "analyst")
            bodies = [json.dumps(self.call(p, who="manager")[1]) for p in ("/api/status", "/api/health", "/api/audit", "/api/decisions", "/api/assistant")]
        self.assertFalse([b for b in bodies if "secret-key-123" in b])
        self.assertNotIn("secret-key-123", (self.tmp / "rt" / "audit.jsonl").read_text(encoding="utf-8"))
        self.assertNotIn("secret-key-123", (self.tmp / "rt" / "state.json").read_text(encoding="utf-8"))

    def test_connection_test_reports_a_missing_key_and_is_not_open_to_viewers(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            s, r = self.call("/api/llm-test", {}, "analyst")
            self.assertEqual((s, r["ok"], r["category"]), (200, False, "not_configured"))
            self.assertEqual(self.call("/api/llm-test", {}, "viewer")[0], 403)
            self.assertFalse(self.call("/api/status", who="viewer")[1]["llm"]["configured"])

    def test_assistant_endpoints_need_sign_in_and_keep_a_conversation(self):
        self.assertEqual(self.call("/api/assistant", {"message": "hi"})[0], 401)
        with mock.patch.dict(os.environ, {}, clear=True):
            s, a = self.call("/api/assistant", {"message": "How is the ICU?", "language": "en"}, "viewer")
        self.assertEqual((s, a["mode"], a["intent"]), (200, "local", "beds"))
        self.assertEqual(len(self.call("/api/assistant", who="viewer")[1]["history"]), 2)
        self.call("/api/assistant/reset", {}, "viewer")
        self.assertEqual(self.call("/api/assistant", who="viewer")[1]["history"], [])
        self.assertEqual(self.call("/api/assistant", {"message": ""}, "viewer")[0], 400)

    # ── static files, headers, validation ──
    def test_dashboard_and_static_assets(self):
        base = f"http://127.0.0.1:{self.port}"
        with urllib.request.urlopen(base + "/") as r:
            html, csp = r.read().decode(), r.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertFalse([w for w in html.split() if w.startswith(("src=\"http", "href=\"http"))])
        for bad in ("/static/app.css", "/static/app.js", "/static/charts.js", "/static/i18n.js",
                    "/static/../app.py", "/static/%2e%2e/app.py", "/static/missing.js", "/static/"):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(base + bad)
            self.assertEqual(cm.exception.code, 404, bad)

    def test_validation_errors(self):
        bad = [("/api/run", {"multiplier": 999}), ("/api/run", {"unit": "OR"}), ("/api/run", {"as_of": "nope"}),
               ("/api/run", {"as_of": "2030-01-01T00:00"}), ("/api/simulate", {"multiplier": "x"}),
               ("/api/policies", {"unit": "ICU", "value": -1}), ("/api/policies", {"unit": "ICU", "value": "abc"}),
               ("/api/policies", {"unit": "XXX", "value": 2})]
        for path, body in bad:
            who = "manager" if "policies" in path else "analyst"
            self.assertEqual(self.call(path, body, who)[0], 400, (path, body))
        self.assertEqual(self.call("/api/run", raw=b"{not json", who="analyst")[0], 400)
        self.assertEqual(self.call("/api/run", raw=b"[1]", who="analyst")[0], 400)
        self.assertEqual(self.call("/api/nope", who="viewer")[0], 404)
        self.assertEqual(self.call("/api/decisions/DEC-x", who="viewer")[0], 404)
        self.assertEqual(self.call("/api/decisions/DEC-x/approve", {}, "manager")[0], 404)
        self.assertEqual(self.call("/api/rollback", {}, "manager")[0], 409)

    def test_invalid_scenario_intervention_returns_clear_400(self):
        status, body = self.call("/api/simulate", {"interventions": [
            {"type": "demand_change", "unit": "ICU", "x": "many"}]}, "analyst")
        self.assertEqual(status, 400)
        self.assertIn("demand_change", body["error"])
        self.assertIn("x", body["error"])

    def test_policy_roundtrip_and_removal(self):
        self.call("/api/policies", {"unit": "ICU", "value": 2}, "manager")
        pol = self.call("/api/policies", who="viewer")[1]["nurse_ratio"]
        self.assertEqual((pol[0]["unit"], pol[0]["value"]), ("ICU", 2.0))
        self.assertIn("NOT an approved", pol[0]["source"])
        self.assertIn("manager", pol[0]["source"])
        self.call("/api/policies", {"unit": "ICU", "value": None}, "manager")
        rows = self.call("/api/policies", who="viewer")[1]["nurse_ratio"]
        self.assertEqual([(r["unit"], r["value"], r["approved"]) for r in rows], [("ER", None, False)])


if __name__ == "__main__":
    unittest.main()
