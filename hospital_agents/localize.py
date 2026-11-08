"""Render a finished Decision's human-readable text in each supported language.

The decision is computed once; its reasons are structured `Msg` objects, so the same decision can be
shown in Arabic or English without re-running anything and without changing a single number.
`texts` is stored with the decision; `overlay` swaps the requested language into the JSON view.
"""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import PoolAdjustment, Reschedule
from .explain import build_evidence
from .messages import LANGS, Msg, codes, render, render_all


def has_sandbox_effect(accepted) -> bool:
    return any(isinstance(a, (PoolAdjustment, Reschedule)) for p in accepted for a in p.actions)


def no_action_reason(decision) -> Msg | None:
    """Why a decision has nothing to apply (None when it has something to apply)."""
    if has_sandbox_effect(decision.accepted):
        return None
    if decision.accepted:
        return Msg("none.reason.advisory")
    if decision.rejected:
        return Msg("none.reason.all_rejected", n=len(decision.rejected))
    return Msg("none.reason.no_proposals")


def _summary(decision, lang: str, created_lang: str) -> str:
    if lang == created_lang:
        return decision.explanation.text
    ev = build_evidence(_facts(decision), lang)
    return " ".join(ev[k] for k in sorted(ev))


def _facts(decision) -> dict:
    from .contracts import to_jsonable
    return {**to_jsonable(decision.card), "needs_human_approval": no_action_reason(decision) is None}


def decision_texts(decision, created_lang: str = "en") -> dict[str, Any]:
    out: dict[str, Any] = {}
    reason = no_action_reason(decision)
    for lang in LANGS:
        out[lang] = {
            "accepted": [{"title": render(p.title, lang), "rationale": render_all(p.rationale, lang)} for p in decision.accepted],
            "rejected": [{"title": render(r.proposal.title, lang), "reasons": render_all(r.reasons, lang)} for r in decision.rejected],
            "reports": [{"agent": r.agent, "notes": render_all(r.notes, lang)} for r in decision.reports],
            "card": {k: render_all(getattr(decision.card, k), lang) for k in ("assumptions", "unverified", "warnings", "recommended_actions")},
            "summary": _summary(decision, lang, created_lang),
            "no_action_reason": render(reason, lang) if reason else None,
        }
    return out


def reason_codes(decision) -> list[list[str]]:
    return [[c for m in r.reasons for c in codes(m)] for r in decision.rejected]


def overlay(view: dict, texts: Mapping[str, Any], lang: str) -> dict:
    """The view with every human-readable string in `lang` (falls back to what is stored)."""
    t = texts.get(lang) or texts.get("en")
    if not t:
        return view
    v = dict(view)
    v["accepted"] = [{**p, "title": x["title"], "rationale": x["rationale"]} for p, x in zip(view["accepted"], t["accepted"])]
    v["rejected"] = [{**r, "proposal": {**r["proposal"], "title": x["title"]}, "reasons": x["reasons"]} for r, x in zip(view["rejected"], t["rejected"])]
    v["reports"] = [{**r, "notes": x["notes"]} for r, x in zip(view["reports"], t["reports"])]
    v["card"] = {**view["card"], **t["card"], "summary": t["summary"]}
    v["explanation"] = {**view["explanation"], "text": t["summary"]}
    v["no_action_reason"] = t["no_action_reason"]
    v["lang"] = lang if lang in texts else "en"
    return v
