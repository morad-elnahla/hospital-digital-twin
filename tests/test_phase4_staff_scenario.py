from dataclasses import replace

from hospital_agents.contracts import Pool
from phase4_helpers import app_and_snapshot


def test_remove_two_rostered_icu_doctors_changes_coverage_without_wait_claim():
    temp, app, as_of, snapshot = app_and_snapshot()
    try:
        pools = dict(snapshot.pools)
        pools["ICU:doctors"] = Pool("ICU:doctors", 3)
        snapshot = replace(snapshot, pools=pools)
        scenario = app.parse_scenario({"as_of": as_of.isoformat(), "interventions": [
            {"type": "staff_change", "unit": "ICU", "role": "DOCTOR", "delta": -2}]})
        out = app._scenario_core(as_of, scenario, snapshot)
        assert out["staff_delta"]["ICU:doctors"] == -2
        assert out["wait_revenue_overtime"]["wait"]["status"] == "unavailable"
        assert "calibrated" in out["wait_revenue_overtime"]["wait"]["reason"]
    finally:
        temp.cleanup()
