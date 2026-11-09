from phase4_helpers import app_and_snapshot


def test_combined_staff_cut_demand_surge_and_move_rejects_violations_and_is_monotone():
    temp, app, as_of, snapshot = app_and_snapshot()
    try:
        one = app.parse_scenario({"unit": "ICU", "multiplier": 1.3})
        twelve = app.parse_scenario({"unit": "ICU", "multiplier": 12})
        low = app._scenario_core(as_of, one, snapshot)
        high = app._scenario_core(as_of, twelve, snapshot)
        assert low == app._scenario_core(as_of, one, snapshot)
        assert high["bed_demand"]["ICU"]["shortfall"] >= low["bed_demand"]["ICU"]["shortfall"]
        assert high["bed_demand"]["ICU"]["demand"] > low["bed_demand"]["ICU"]["demand"]
        assert high["bed_demand"]["ICU"]["label"] == "assumption: unvalidated baseline forecast"
        assert low["bed_demand"]["ICU"]["why_nothing_moved"]
        assert low["bed_demand"]["ICU"]["what_would_help"]

        booking = next((b for b in snapshot.bookings if b.slot.domain == "OR"), None)
        destination = next((s for s in snapshot.slots if booking and s.key.domain == "OR"
                            and s.key.resource_id != booking.slot.resource_id
                            and s.key.start > as_of), None)
        interventions = [
            {"type": "staff_change", "unit": "ICU", "role": "DOCTOR", "delta": -1000},
            {"type": "demand_change", "unit": "ICU", "x": 12},
        ]
        if booking and destination:
            interventions.append({"type": "reschedule_surgery", "booking_id": booking.id,
                                  "target": {"domain": "OR", "resource_id": destination.key.resource_id,
                                             "start": destination.key.start.isoformat()}})
        scenario = app.parse_scenario({"as_of": as_of.isoformat(), "interventions": interventions})
        out = app._scenario_core(as_of, scenario, snapshot)
        assert len(out["rejected"]) >= 1
        assert any("rostered" in x["reason"] for x in out["rejected"])
        if booking and destination:
            assert any(any(token in x["reason"].lower() for token in ("team", "specialty", "slot"))
                       for x in out["rejected"])
    finally:
        temp.cleanup()


def test_contract_rejects_invalid_ids_ranges_and_time_shapes():
    temp, app, _, _ = app_and_snapshot()
    try:
        for body in (
            {"horizon": 31},
            {"seed": -1},
            {"interventions": [{"type": "bed_change", "unit": "ICU", "delta": 2.5}]},
            {"interventions": [{"type": "reschedule_surgery", "booking_id": "missing", "target": {}}]},
        ):
            try:
                app.parse_scenario(body)
            except Exception as error:
                assert getattr(error, "status", None).value == 400
            else:
                raise AssertionError(f"invalid scenario accepted: {body}")
    finally:
        temp.cleanup()


def test_run_persists_versioned_input_and_replays_with_same_seed():
    import json
    import sqlite3
    from contextlib import closing

    temp, app, as_of, snapshot = app_and_snapshot()
    try:
        result = app.simulate({"as_of": as_of.isoformat(), "unit": "ICU", "multiplier": 1,
                               "seed": 17, "interventions": [{"type": "demand_change", "unit": "ICU", "x": 1.3}]})
        with closing(sqlite3.connect(app.twin.t.path)) as conn:
            saved = conn.execute("SELECT parameters_json,results_json,random_seed FROM simulation_runs WHERE simulation_id=?",
                                 (result["simulation_id"],)).fetchone()
            events = conn.execute("SELECT COUNT(*) FROM simulation_events WHERE simulation_id=?",
                                  (result["simulation_id"],)).fetchone()[0]
        parameters, saved_result, seed = json.loads(saved[0]), json.loads(saved[1]), saved[2]
        assert parameters["data_version"] and parameters["policy_version"]
        assert seed == 17 and events == 2
        replay = app.replay_simulation(result["simulation_id"])
        assert replay["core"] == saved_result["core"]
    finally:
        temp.cleanup()
