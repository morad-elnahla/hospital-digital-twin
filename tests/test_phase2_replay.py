"""Replay decisions use as-of inputs and fail closed when OR teams are not identified."""
import asyncio
import dataclasses
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path

from hospital_agents import Orchestrator, Settings
from hospital_agents.agents import ORAgent
from hospital_agents.arbitration import CheckContext
from hospital_agents.constraints import SlotAvailability
from hospital_agents.contracts import (Booking, PolicyBundle, Proposal, Reschedule, Slot, SlotKey,
                                       TwinSnapshot, Urgency, make_id)
from hospital_agents.messages import Msg, codes
from hospital_agents.twin_data import Scenario, TwinData, _planned_icu_need

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "runtime" / "hdt.sqlite"
T0 = datetime(2026, 10, 15, 10)

class ReplayAsOf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.twin = TwinData(DB)

    def test_icu_need_uses_planned_surgery_fields_only(self):
        row = {"icu_bed_required": "False", "post_op_destination": "WARD"}
        self.assertIs(_planned_icu_need(row), False)
        row["icu_bed_required"] = "True"
        row["post_op_destination"] = "ICU"
        self.assertIs(_planned_icu_need(row), True)
        row["post_op_destination"] = "WARD"
        self.assertIsNone(_planned_icu_need(row))  # conflicting plan remains unknown
        snap = self.twin.snapshot(T0)
        source_rows = {r["surgery_id"]: r for r in self.twin.t["surgeries"]}
        for booking in (b for b in snap.bookings if b.slot.domain == "OR"):
            self.assertEqual(booking.needs_icu_bed, _planned_icu_need(source_rows[booking.id]))

    def test_post_as_of_actuals_and_metrics_do_not_change_the_decision(self):
        with tempfile.TemporaryDirectory() as folder:
            clone = Path(folder) / "changed.sqlite"
            shutil.copyfile(DB, clone)
            with closing(sqlite3.connect(clone)) as conn:
                conn.execute("UPDATE daily_metrics SET occupancy_rate=0.01 WHERE metric_date > ? AND occupancy_rate IS NOT NULL",
                             (T0.date().isoformat(),))
                conn.execute("UPDATE surgeries SET status='CANCELLED', actual_start='2026-11-01T08:00:00', actual_end='2026-11-01T09:00:00' WHERE planned_start > ?",
                             (T0.isoformat(),))
                future_icu = conn.execute("SELECT DISTINCT visit_id FROM bed_stays WHERE start_time > ? AND bed_id LIKE 'BED-ICU%' LIMIT 1",
                                          (T0.isoformat(),)).fetchone()
                self.assertIsNotNone(future_icu, "fixture needs a future ICU stay to perturb")
                conn.execute("UPDATE bed_stays SET bed_id='BED-WARD-01-01' WHERE visit_id=? AND start_time > ?",
                             (future_icu[0], T0.isoformat()))
                conn.commit()
            changed = TwinData(clone)
            self.assertNotEqual(self.twin.historical_icu_visits, changed.historical_icu_visits)
            base_inputs = self.twin.inputs(T0, Scenario("ICU", 1.3))
            changed_inputs = changed.inputs(T0, Scenario("ICU", 1.3))
            base_decision = asyncio.run(Orchestrator(Settings(language="en")).run(base_inputs))
            changed_decision = asyncio.run(Orchestrator(Settings(language="en")).run(changed_inputs))
            self.assertEqual(dataclasses.replace(base_decision, created_at=changed_decision.created_at), changed_decision)

    def test_clinic_capacity_drops_when_no_doctor_is_rostered_on_slot(self):
        clinic = self.twin.dept_by_type["CLINIC"]
        appointments = [r for r in self.twin.t["appointments"]
                        if r["department_id"] == clinic and r["scheduled_start"][:10] >= T0.date().isoformat()]
        self.assertTrue(appointments)
        key_start = datetime.fromisoformat(appointments[0]["scheduled_start"][:13] + ":00:00")
        key = SlotKey("CLINIC", clinic, key_start)
        original_shifts = self.twin.shifts
        self.addCleanup(setattr, self.twin, "shifts", original_shifts)
        self.twin.shifts = [s for s in original_shifts
                            if self.twin.staff_role[s[2]] != (clinic, "DOCTOR")]
        slots, _ = self.twin.calendar(T0)
        self.assertEqual(next(s.capacity for s in slots if s.key == key), 0)

    def test_or_move_without_identified_team_is_unverifiable_and_rejected(self):
        source = SlotKey("OR", "OR-01", datetime(2026, 10, 16))
        target = SlotKey("OR", "OR-01", datetime(2026, 10, 25))
        booking = Booking("SUR-TEST", source, Urgency.NON_URGENT, None, True, 60,
                          specialty="GENERAL")
        slots = (Slot(source, datetime(2026, 10, 17), 600, 100, specialty="GENERAL"),
                 Slot(target, datetime(2026, 10, 26), 600, 0, specialty="GENERAL"))
        twin = TwinSnapshot(T0, "test", {}, slots, (booking,), datetime(2026, 11, 11))
        action = Reschedule(booking.id, source, target)
        proposal = Proposal(make_id("or", (action,)), "or", "test", (action,), ("test",))
        result = SlotAvailability().check(CheckContext(twin, PolicyBundle()), [proposal])
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0].message, Msg)
        self.assertIn("slot.team_unverifiable", codes(result[0].message))
        self.assertIn("UNVERIFIABLE", str(result[0].message))

    def test_specialty_mismatch_is_rejected(self):
        source = SlotKey("OR", "OR-01", datetime(2026, 10, 16))
        target = SlotKey("OR", "OR-02", datetime(2026, 10, 25))
        booking = Booking("SUR-TEST", source, Urgency.NON_URGENT, "surgeon-1", True, 60,
                          specialty="GENERAL")
        slots = (Slot(source, datetime(2026, 10, 17), 600, 100, specialty="GENERAL"),
                 Slot(target, datetime(2026, 10, 26), 600, 0, provider_ids=("surgeon-1",), specialty="ORTHOPEDIC"))
        twin = TwinSnapshot(T0, "test", {}, slots, (booking,), datetime(2026, 11, 11))
        action = Reschedule(booking.id, source, target)
        proposal = Proposal(make_id("or", (action,)), "or", "test", (action,), ("test",))
        result = SlotAvailability().check(CheckContext(twin, PolicyBundle()), [proposal])
        self.assertIn("slot.specialty", codes(result[0].message))

if __name__ == "__main__":
    unittest.main()
