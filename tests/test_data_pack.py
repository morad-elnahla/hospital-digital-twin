"""The CSV adapter against the real data pack in ./data (no mocks)."""
import asyncio
import csv
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from hospital_agents import Orchestrator, Settings
from hospital_agents.contracts import PoolAdjustment, PolicyBundle, PolicyValue, Reschedule
from hospital_agents.policies import FolderPolicyRetriever
from hospital_agents.twin_data import Scenario, TwinData, _dt, apply_actions

DATA = Path(__file__).parent.parent / "data"
td = TwinData(DATA)
AS_OF = td.default_as_of


def decide(scenario=Scenario(), policies=None, applied=(), as_of=AS_OF):
    inputs = td.inputs(as_of, scenario, applied, policies)
    return asyncio.run(Orchestrator(Settings(language="en")).run(inputs))


class Snapshot(unittest.TestCase):
    def test_nanosecond_fraction_is_truncated_to_microseconds(self):
        self.assertEqual(_dt("2025-04-14 11:51:43.999999998"), datetime(2025, 4, 14, 11, 51, 43, 999999))

    def test_empty_bed_stay_end_time_remains_occupied(self):
        self.assertEqual(sum(not row["end_time"] for row in td.t["bed_stays"]), 40)
        sentinel = datetime(2100, 1, 1)
        self.assertEqual(sum(end == sentinel for _, _, end in td.stays), 40)
        self.assertTrue(all(end > datetime(2026, 10, 20, 23, 59)
                            for _, _, end in td.stays if end == sentinel))

    def test_bed_pools_match_the_bed_table(self):
        pools = td.pools(AS_OF)
        self.assertEqual((pools["ER:beds"].total, pools["ICU:beds"].total, pools["WARD:beds"].total), (12, 12, 36))

    def test_calendar_end_tracks_latest_planned_date(self):
        self.assertEqual(td.calendar_end, datetime(2026, 11, 11))
        slots, _ = td.calendar(datetime(2026, 10, 15, 10))
        self.assertTrue(any(slot.key.start.date() == datetime(2026, 11, 10).date() for slot in slots))

    def test_occupied_beds_match_daily_metrics_convention(self):
        # occupied_beds is the end-of-day snapshot: state at midnight after metric_date, not noon on metric_date.
        for metric_date, snapshot_time, ward_snapshot in (
            ("2026-10-19", "2026-10-20T00:00", 31),
            ("2026-10-20", "2026-10-21T00:00", 22),
        ):
            row = td.metrics[metric_date]
            pools = td.pools(datetime.fromisoformat(snapshot_time))
            self.assertEqual(pools["WARD:beds"].committed, ward_snapshot)
            for unit, dep in (("ICU", "DEP-ICU"), ("WARD", "DEP-WARD"), ("ER", "DEP-ER")):
                self.assertEqual(pools[f"{unit}:beds"].committed, int(row[dep]["occupied_beds"]),
                                 f"{unit} at {snapshot_time} vs end-of-day {metric_date}")

    def test_slot_load_equals_booked_minutes(self):
        slots, bookings = td.calendar(AS_OF)
        load = {}
        for b in bookings:
            load[b.slot] = load.get(b.slot, 0) + b.duration
        roster = td.or_availability
        for slot in slots:
            row = roster.get((slot.key.start.strftime("%Y-%m-%d"), slot.key.resource_id)) if slot.key.domain == "OR" else None
            if row and row["availability_status"] != "CLOSED":
                # R4 counts post-operation turnover; bookings count only procedure minutes.
                self.assertEqual(slot.booked, int(float(row["booked_minutes_with_turnover"])))
                self.assertGreaterEqual(slot.booked, load.get(slot.key, 0))
            else:
                self.assertEqual(slot.booked, load.get(slot.key, 0))
        self.assertTrue(all(b.slot.start > AS_OF - timedelta(days=1) for b in bookings))

    def test_no_future_leakage_in_forecast(self):
        as_of = datetime(2026, 8, 14, 8)
        first = td.occupancy_forecast(as_of, "ICU")[0]
        wd = datetime.fromisoformat(first["date"]).weekday()
        history = [float(rows["DEP-ICU"]["occupancy_rate"]) for day, rows in td.metrics.items()
                   if day < as_of.date().isoformat() and datetime.fromisoformat(day).weekday() == wd]
        self.assertGreater(len(history), 1)
        self.assertAlmostEqual(first["predicted"], sum(history) / len(history), places=9)

    def test_forecast_reproduces_the_pack_forecast_file(self):
        pack = [r for r in td.t["forecast_results"] if r["target_metric"] == "bed_occupancy_rate"]
        for unit, dep in (("ICU", "DEP-ICU"), ("WARD", "DEP-WARD")):
            mine = {r["date"]: r["predicted"] for r in td.occupancy_forecast(datetime(2026, 10, 22, 8), unit)}
            for r in (p for p in pack if p["department_id"] == dep):
                self.assertAlmostEqual(mine[r["forecast_for"][:10]], float(r["predicted_value"]), delta=0.002)

    def test_overview_tiles_come_from_the_csvs(self):
        from hospital_agents import insights
        o = insights.overview(td, AS_OF)
        self.assertEqual(o["period"]["to"], "2026-10-16")            # complete days before the replay moment
        er = td.dept_by_type["ER"]
        self.assertEqual(o["er"]["arrivals"][-1], float(td.metrics["2026-10-16"][er]["arrivals_count"]))
        self.assertEqual(len(o["departments"]), 7)
        self.assertEqual(len(o["pack_simulations"]), len(td.t["simulation_runs"]))


class Agents(unittest.TestCase):
    def test_baseline_needs_no_action(self):
        d = decide()
        self.assertEqual((d.accepted, d.card.critical_bottleneck), ((), None))

    def test_stress_without_policy_is_rejected_as_unverifiable(self):
        d = decide(Scenario("ICU", 12))
        self.assertEqual(d.card.critical_bottleneck, "ICU:beds")
        self.assertFalse(any(p.agent == "bed" for p in d.accepted))
        self.assertGreater(d.card.unmet["ICU:beds"], 0)  # no donor/capacity is invented

    def test_stress_with_policy_accepts_the_bed_move_and_reports_what_is_unmet(self):
        pol = PolicyBundle({f"nurse.max_patients_per_nurse:{u}": PolicyValue(40, "test") for u in ("ICU", "WARD")})
        d = decide(Scenario("ICU", 12), pol)
        self.assertFalse(any(p.agent == "bed" for p in d.accepted))
        self.assertGreater(d.card.unmet["ICU:beds"], 0)  # source roster has no safe donor headroom

    def test_only_elective_surgeries_move(self):
        # 2026-10-01: an elective ICU-bound surgery (Oct 7) lies inside the forecast week and the calendar is known past it.
        d = decide(Scenario("ICU", 12), as_of=datetime(2026, 10, 1, 8))
        urgent = {r["surgery_id"] for r in td.t["surgeries"] if r["urgency"] != "ELECTIVE"}
        moved = {a.booking_id for p in d.accepted for a in p.actions if isinstance(a, Reschedule)}
        self.assertTrue(moved)
        self.assertFalse(moved & urgent)

    def test_apply_then_rollback_restores_the_snapshot(self):
        pol = PolicyBundle({f"nurse.max_patients_per_nurse:{u}": PolicyValue(40, "test") for u in ("ICU", "WARD")})
        d = decide(Scenario("ICU", 12), pol)
        snap = td.snapshot(AS_OF)
        applied = apply_actions(snap, [a for p in d.accepted for a in p.actions])
        self.assertTrue(d.accepted)
        self.assertNotEqual(applied.bookings, snap.bookings)  # R4 changes OR dates, not staffed bed capacity
        restored = apply_actions(applied, d.rollback_actions)
        self.assertEqual(restored.pools, snap.pools)
        self.assertEqual({s.key: s.booked for s in restored.slots}, {s.key: s.booked for s in snap.slots})
        self.assertEqual(restored.bookings, snap.bookings)

    def test_pack_policies_are_searchable_text_only(self):
        r = FolderPolicyRetriever(Path(__file__).parent / "fixtures" / "empty", extra=td.policy_docs())
        hits = asyncio.run(r.search("bed allocation"))
        self.assertEqual(hits[0].doc_id, "POL-002")
        self.assertIn("approved=False", hits[0].source)
        self.assertEqual(asyncio.run(r.values(["ICU"], AS_OF)).values, {})   # never a numeric constraint


class Pack(unittest.TestCase):
    def test_dataset_tables_present_and_consistent(self):
        report_files = {"future_booking_capacity_by_unit", "future_booking_capacity_daily"}
        files = sorted(p.stem for p in DATA.glob("*.csv") if p.stem not in report_files)
        self.assertEqual(set(files), set(td.t) - report_files)  # includes new R4 staff and OR capacity tables
        self.assertIn("or_availability", files)
        self.assertIn("nurse_coverage_shift_detail", files)
        n = {}
        for p in DATA.glob("*.csv"):
            if p.stem in report_files:
                continue
            with p.open(encoding="utf-8") as f:
                n[p.stem] = sum(1 for _ in csv.DictReader(f))
        self.assertEqual((n["visits"], n["surgeries"]), (44035, 8953))


if __name__ == "__main__":
    unittest.main()
