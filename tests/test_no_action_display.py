"""Regression tests for the NO_ACTION display fixes.

The "requires human approval" sentence must appear only for decisions that actually
wait for approval — never for an auto-closed NO_ACTION decision. The decisions()-list
fields (no_action_code, unmet) are verified against the live server in the acceptance run.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from hospital_agents.explain import build_evidence  # noqa: E402

APPROVAL_AR = "يتطلب اعتماد بشري"
APPROVAL_EN = "Requires human approval"

BASE_FACTS = {
    "decision_id": "dec-test",
    "recommended_actions": ("do something",),
    "rejected_count": 0,
    "critical_bottleneck": "ICU",
    "expected_demand_change_pct": 120,
    "unmet": {"ICU": 2},
    "waiting_minutes_saved": None,
    "confidence": None,
}


def test_approval_sentence_present_when_decision_needs_approval():
    for lang in ("ar", "en"):
        ev = build_evidence({**BASE_FACTS, "needs_human_approval": True}, lang)
        assert "E7" in ev, f"E7 missing for {lang}"


def test_approval_sentence_absent_for_auto_closed_no_action():
    for lang in ("ar", "en"):
        ev = build_evidence({**BASE_FACTS, "needs_human_approval": False}, lang)
        assert "E7" not in ev, f"E7 should be absent for {lang}"
        text = " ".join(ev.values())
        assert APPROVAL_AR not in text and APPROVAL_EN not in text


def test_approval_sentence_absent_when_flag_missing():
    # A facts dict without the flag must not claim approval is needed.
    ev = build_evidence(BASE_FACTS, "ar")
    assert "E7" not in ev
