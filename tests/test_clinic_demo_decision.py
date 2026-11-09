from hospital_agents.auth import Principal
from phase4_helpers import app_and_snapshot


def test_clinic_scheduling_demo_decision_approves_and_rolls_back_verified_moves():
    temp, app, as_of, _ = app_and_snapshot()
    try:
        manager = Principal("demo-manager", "operations_manager")
        decision = app.run({"as_of": as_of.isoformat(), "unit": "CLINIC", "multiplier": 1,
                            "seed": 0, "language": "en"})
        assert decision["scenario"]["unit"] == "CLINIC"
        assert decision["status"] == "PENDING"
        assert decision["accepted"]
        assert all(a["from_slot"]["domain"] == "CLINIC"
                   for p in decision["accepted"] for a in p["actions"])
        legacy_bed_scenario = {**app.store.records[decision["id"]],
                               "scenario": {**app.store.records[decision["id"]]["scenario"], "unit": "ICU"}}
        assert "unrelated to the bed-demand scenario" in app._gate_refusal(legacy_bed_scenario)
        approved = app.approve(decision["id"], {"note": "Local demo approval"}, manager)
        assert approved["status"] == "APPLIED"
        assert app.sandbox()["applied"]
        rolled_back = app.rollback({"note": "Local demo rollback"}, manager)
        assert rolled_back["status"] == "ROLLED_BACK"
        assert app.sandbox()["applied"] == []
    finally:
        temp.cleanup()
