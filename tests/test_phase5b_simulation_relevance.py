from phase4_helpers import app_and_snapshot


def test_icu_x12_marks_unrelated_appointments_and_reports_unresolved_residual():
    temp, app, as_of, _ = app_and_snapshot()
    try:
        result = app.simulate({"as_of": as_of.isoformat(), "unit": "ICU", "multiplier": 12, "seed": 0})
        assert result["core"]["bed_demand"]["ICU"]["residual_message"] == {
            "code": "unresolved_shortfall", "params": {"beds": 101}}
        assert result["core"]["bed_demand"]["ICU"]["what_would_help"]
        assert result["scenario_relevant_actions"] == []
        assert len(result["not_related_actions"]) == 5
        assert all(a["agent"] == "appointment" and a["label_code"] == "not_related_action"
                   for a in result["not_related_actions"])
        assert result["decision"]["accepted"] == []
        assert result["decision"]["card"]["recommended_actions"] == []
    finally:
        temp.cleanup()


def test_icu_x13_decision_card_has_zero_scenario_actions():
    temp, app, as_of, _ = app_and_snapshot()
    try:
        result = app.simulate({"as_of": as_of.isoformat(), "unit": "ICU", "multiplier": 1.3, "seed": 0})
        assert result["decision"]["accepted"] == []
        assert result["decision"]["card"]["recommended_actions"] == []
        assert all(not report["proposals"] for report in result["decision"]["reports"])
    finally:
        temp.cleanup()


def test_scenario_lab_created_decision_excludes_clinic_moves():
    from hospital_agents.auth import Principal

    temp, app, as_of, _ = app_and_snapshot()
    try:
        result = app.run({"as_of": as_of.isoformat(), "unit": "ICU", "multiplier": 1.3,
                         "language": "en", "scenario_lab": True}, Principal("clinician", "clinician"))
        assert not any(action.get("from_slot", {}).get("domain") == "CLINIC"
                       for proposal in result["accepted"] for action in proposal["actions"])
    finally:
        temp.cleanup()
