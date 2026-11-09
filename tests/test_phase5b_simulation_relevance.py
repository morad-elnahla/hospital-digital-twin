from phase4_helpers import app_and_snapshot


def test_icu_x12_marks_unrelated_appointments_and_reports_unresolved_residual():
    temp, app, as_of, _ = app_and_snapshot()
    try:
        result = app.simulate({"as_of": as_of.isoformat(), "unit": "ICU", "multiplier": 12, "seed": 0})
        assert result["core"]["bed_demand"]["ICU"]["residual_message"] == (
            "unresolved shortfall 101 beds: no verified action can cover it; needs manager/escalation")
        assert result["core"]["bed_demand"]["ICU"]["what_would_help"]
        assert result["scenario_relevant_actions"] == []
        assert len(result["not_related_actions"]) == 5
        assert all(a["agent"] == "appointment" and a["label"] == "not related to this scenario"
                   for a in result["not_related_actions"])
        accepted = result["decision"]["accepted"]
        assert all(p.get("scenario_relevance") == "not related to this scenario" for p in accepted)
    finally:
        temp.cleanup()
