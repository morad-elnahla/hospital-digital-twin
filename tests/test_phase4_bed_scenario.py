from phase4_helpers import app_and_snapshot


def test_bed_increase_is_assumption_without_ceiling_or_staffing_authorization():
    temp, app, as_of, snapshot = app_and_snapshot()
    try:
        before = snapshot.pools["ICU:beds"].total
        scenario = app.parse_scenario({"as_of": as_of.isoformat(), "interventions": [
            {"type": "bed_change", "unit": "ICU", "delta": 2}]})
        out = app._scenario_core(as_of, scenario, snapshot)
        assert out["notes"][0]["status"] == "assumed"
        assert out["bed_demand"]["ICU"]["beds"] == before
        assert "assumption: unvalidated baseline forecast" == out["bed_demand"]["ICU"]["label"]
        assert out["bed_demand"]["ICU"]["shortfall"] is not None
    finally:
        temp.cleanup()
