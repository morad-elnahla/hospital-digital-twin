from phase4_helpers import app_and_snapshot


def test_er_arrival_surge_reports_unavailable_bed_relation_and_bed_addition_is_assumption_only():
    temp, app, as_of, snapshot = app_and_snapshot()
    try:
        surged = app._scenario_core(as_of, app.parse_scenario({"interventions": [
            {"type": "er_arrivals_surge", "x": 1.3}]}), snapshot)
        assert round(surged["er_arrivals"]["baseline_mean"], 1) == 66.0
        assert round(surged["er_arrivals"]["scenario_mean"], 1) == 85.8
        assert surged["er_arrivals"]["bed_impact"] == {
            "status": "unavailable", "reason_code": "er_bed_relation_not_calibrated", "reason_params": {}}

        original_beds = snapshot.pools["ICU:beds"].total
        assumed = app._scenario_core(as_of, app.parse_scenario({"unit": "ICU", "multiplier": 12,
            "interventions": [{"type": "bed_change", "unit": "ICU", "delta": 12}]}), snapshot)
        row = assumed["bed_demand"]["ICU"]
        what_if = row["bed_addition_assumption"]
        assert row["beds"] == original_beds
        assert row["shortfall"] == max(0, __import__("math").ceil(row["demand"] - 1e-9) - original_beds)
        assert what_if["status"] == "assumption" and what_if["template_approved"] is False
        assert what_if["shortfall"] == max(0, row["shortfall"] - 12)
        assert (what_if["nurses_needed"], what_if["nurses_on_shift"], what_if["observed_patients_per_nurse"]) == (12, 5, 4.8)
    finally:
        temp.cleanup()


def test_baseline_ratio_warning_reports_observed_value_and_unapproved_ratio_in_arabic():
    from hospital_agents.card import baseline_ratio_warnings
    temp, app, as_of, snapshot = app_and_snapshot()
    try:
        scenario = app.parse_scenario({"as_of": as_of.isoformat(), "unit": "ICU", "multiplier": 1.3})
        inputs = app._inputs(as_of, scenario)
        warnings = baseline_ratio_warnings(inputs)
        icu = next((item.render("ar") for item in warnings if item.params.get("unit") == "ICU"), None)
        assert icu is not None
        assert "2:1" in icu and "غير المعتمدة" in icu
        assert "2.4" in icu and "12 سرير" in icu and "5 ممرض" in icu
    finally:
        temp.cleanup()
