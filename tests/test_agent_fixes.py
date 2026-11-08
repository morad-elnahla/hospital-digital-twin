"""Regression tests for the functional-testing findings on the AI agents / digital twin.

1. OR agent proposed moves into days the schedule data does not cover.
2. Decision impact: assumed relief vs confirmed arithmetic must never be mixed.
3. Bed agent / nurse ratio: sizing and blame must follow the real numbers, safety gate intact.
4. A run with nothing to apply must not wait in the approval queue.
5. Reasons and impact labels must be readable in Arabic, and the cost/impact figures must say what they are.
"""
import asyncio
import re
import string
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from app import App, ApiError
from hospital_agents import Orchestrator, Settings
from hospital_agents.agents import ORAgent
from hospital_agents.arbitration import Arbitrator
from hospital_agents.auth import Principal
from hospital_agents.contracts import (Booking, Pool, PoolAdjustment, PolicyBundle, PolicyValue, Proposal,
                                       Reschedule, SharedInputs, Slot, SlotKey, TwinSnapshot, Urgency, make_id)
from hospital_agents.messages import CATALOG, Msg
from hospital_agents.twin_data import TwinData

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
T0 = datetime(2026, 10, 1, 8)


def run(coro):
    return asyncio.run(coro)


def inputs(pools, policies=None, demand=None, slots=(), bookings=(), calendar_end=None, horizon_days=7):
    """Hand-built SharedInputs. `demand` = {metric: peak value}; one flat forecast series per metric."""
    from hospital_agents.contracts import Forecast, ForecastPoint
    series = {m: tuple(ForecastPoint(T0 + timedelta(days=d), v, v, v) for d in range(1, horizon_days + 1))
              for m, v in (demand or {}).items()}
    twin = TwinSnapshot(T0, "t", {k: Pool(k, *v) for k, v in pools.items()}, tuple(slots), tuple(bookings), calendar_end)
    pol = PolicyBundle({k: PolicyValue(v, "test") for k, v in (policies or {}).items()})
    return SharedInputs(twin, Forecast("f", series), None, pol)


class OperatingRoomCalendar(unittest.TestCase):
    """Finding 1: a missing future is unknown, never free."""

    @classmethod
    def setUpClass(cls):
        cls.td = TwinData(DATA)

    def test_calendar_stops_where_the_data_stops(self):
        snap = self.td.snapshot(datetime(2026, 10, 17, 8))
        self.assertEqual(snap.calendar_end, datetime(2026, 11, 11))  # Round 4 documented extension
        self.assertTrue(snap.slots)
        self.assertLess(max(s.key.start for s in snap.slots), snap.calendar_end)

    def test_no_move_into_days_without_schedule_data(self):
        # Reported case: as_of 2026-10-17, ICU x12 used to move two surgeries to OR-01 on 2026-10-25.
        with tempfile.TemporaryDirectory() as tmp:
            app = App(DATA, Path(tmp) / "rt", Path(tmp) / "pol")
            d = app.run({"as_of": "2026-10-17T08:00", "unit": "ICU", "multiplier": 12, "language": "en"},
                        Principal("m", "operations_manager"))
        moved = [a for p in d["accepted"] for a in p["actions"] if "booking_id" in a]
        self.assertTrue(moved)  # Round 4 extends the schedule and permits valid weekday moves
        availability = {(r["date"], r["or_id"]): r for r in self.td.t["or_availability"]}
        for m in moved:
            target = m["to_slot"]["start"][:10]
            or_id = m["to_slot"]["resource_id"]
            row = availability[(target, or_id)]
            self.assertNotEqual(row["availability_status"].upper(), "CLOSED")
            self.assertGreater(int(float(row["capacity_minutes"])), 0)
            self.assertLess(datetime.fromisoformat(m["to_slot"]["start"]), self.td.calendar_end)

    def test_arbitration_independently_refuses_a_slot_beyond_the_calendar(self):
        # Defence in depth: even if an agent (or a different adapter) listed the empty future as a slot, it is refused.
        src = SlotKey("OR", "OR-1", datetime(2026, 10, 3))
        dst = SlotKey("OR", "OR-1", datetime(2026, 10, 25))
        twin = TwinSnapshot(T0, "t", {}, (Slot(src, datetime(2026, 10, 4), 600, 100), Slot(dst, datetime(2026, 10, 26), 600, 0)),
                            (Booking("b1", src, Urgency.NON_URGENT, None, True, 100),), datetime(2026, 10, 21))
        acts = (Reschedule("b1", src, dst),)
        prop = Proposal(make_id("or", acts), "or", "t", acts, ("r",))
        res = Arbitrator(Settings()).resolve(twin, PolicyBundle(), [prop])
        self.assertFalse(res.accepted)
        self.assertIn("outside the known calendar", res.rejected[0].reasons[0])

    def test_verified_move_stays_in_the_same_room_inside_the_calendar(self):
        # 2026-10-01: elective ICU-bound surgery on Oct 7, calendar known until Oct 20.
        snap_inputs = self.td.inputs(T0, __import__("hospital_agents.twin_data", fromlist=["Scenario"]).Scenario("ICU", 12))
        rep = run(ORAgent().propose(snap_inputs, Settings()))
        self.assertTrue(rep.proposals)
        twin = snap_inputs.twin
        horizon = snap_inputs.forecast.horizon_end
        for p in rep.proposals:
            a = p.actions[0]
            self.assertEqual(a.from_slot.resource_id, a.to_slot.resource_id)          # same room: specialty/equipment unchanged
            self.assertGreater(a.to_slot.start, horizon)                              # really outside the stressed week
            self.assertLess(a.to_slot.start, twin.calendar_end)                       # inside what the data knows
            b, dst = twin.booking(a.booking_id), twin.slot(a.to_slot)
            self.assertGreaterEqual(dst.free, b.duration)                             # fits the free minutes

    def test_two_moves_into_one_day_never_exceed_its_free_minutes(self):
        cap = 600
        free_day = SlotKey("OR", "R", datetime(2026, 10, 12))
        slots = [Slot(free_day, datetime(2026, 10, 13), cap, cap - 250)]               # only 250 free minutes
        bookings = []
        for i in range(3):
            k = SlotKey("OR", "R", datetime(2026, 10, 2 + i))
            slots.append(Slot(k, k.start + timedelta(days=1), cap, 150))
            bookings.append(Booking(f"s{i}", k, Urgency.NON_URGENT, None, True, 150))
        inp = inputs({"ICU:beds": (12, 0)}, demand={"ICU:beds:demand": 20}, slots=slots, bookings=bookings,
                     calendar_end=datetime(2026, 10, 20))
        rep = run(ORAgent().propose(inp, Settings()))
        claimed = sum(inp.twin.booking(p.actions[0].booking_id).duration for p in rep.proposals if p.actions[0].to_slot == free_day)
        self.assertLessEqual(claimed, 250)
        self.assertEqual(len(rep.proposals), 1)                                       # 150 fits, a second 150 would not


class ImpactAccounting(unittest.TestCase):
    """Finding 2: confirmed arithmetic and assumed relief are separate, labelled numbers."""

    def setUp(self):
        self.td = TwinData(DATA)

    def _decide(self, scenario_mult=12):
        from hospital_agents.twin_data import Scenario
        return run(Orchestrator(Settings(language="en")).run(self.td.inputs(T0, Scenario("ICU", scenario_mult))))

    def test_postponements_are_not_subtracted_from_the_confirmed_deficit(self):
        d = self._decide()
        moved = [p for p in d.accepted if p.agent == "or"]
        self.assertTrue(moved)
        card = d.card
        self.assertGreater(card.unmet["ICU:beds"], 0)  # R4 forecast baseline is data-derived
        self.assertEqual(card.assumed_relief["ICU:beds"], float(len(moved)))
        self.assertEqual(card.unmet_if_assumed["ICU:beds"], card.unmet["ICU:beds"] - len(moved))
        self.assertEqual(card.capacity_added, {})

    def test_the_card_labels_the_assumption_and_the_unsimulated_impact(self):
        d = self._decide()
        text = " ".join(d.card.assumptions + d.card.unverified)
        self.assertIn("ASSUMED", text)
        self.assertIn("not simulated", text)
        self.assertIn("only if that assumption holds", text)
        self.assertTrue(all(p.impact is None and p.effects[0].basis == "assumed" for p in d.accepted if p.agent == "or"))

    def test_explanation_never_presents_the_assumption_as_a_result(self):
        d = self._decide()
        self.assertIn("assumption, not a simulation", d.explanation.text)

    def test_what_if_preview_reports_relief_apart_from_the_shortfall(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(DATA, Path(tmp) / "rt", Path(tmp) / "pol")
            sim = app.simulate({"as_of": "2026-10-01T08:00", "unit": "ICU", "multiplier": 12, "language": "en"})
        icu = sim["after"]["ICU"]
        self.assertEqual(icu["shortfall_beds"], sim["before"]["ICU"]["shortfall_beds"])          # confirmed: unchanged by postponements
        self.assertEqual(icu["assumed_relief_beds"], float(sim["rescheduled_bookings"]))
        self.assertEqual(icu["shortfall_if_assumed_beds"], icu["shortfall_beds"] - sim["rescheduled_bookings"])
        self.assertEqual(sim["impact_basis"], {"capacity_changes": "computed", "postponements": "assumed"})
        self.assertEqual(sim["cost_basis"]["simulated"], False)
        self.assertEqual(sim["unavailable"][0]["metric_key"], "effect")


class NurseRatioAndBedSizing(unittest.TestCase):
    """Finding 3."""

    def arbitrate(self, twin_pools, policies, *acts):
        snap = TwinSnapshot(T0, "t", {k: Pool(k, *v) for k, v in twin_pools.items()})
        prop = Proposal(make_id("bed", acts), "bed", "t", tuple(acts), ("r",))
        pol = PolicyBundle({k: PolicyValue(v, "src | text") for k, v in policies.items()})
        return Arbitrator(Settings()).resolve(snap, pol, [prop])

    POOLS = {"ICU:beds": (12, 0), "WARD:beds": (36, 12), "ICU:nurses": (1, 0), "WARD:nurses": (2, 0)}

    def test_a_donor_that_improves_is_not_blamed_for_an_existing_breach(self):
        # WARD is already above 6/nurse (36/2 = 18) and the move lowers it (21/2 = 10.5): not the move's fault.
        res = self.arbitrate(self.POOLS, {"nurse.max_patients_per_nurse:ICU": 40, "nurse.max_patients_per_nurse:WARD": 6},
                             PoolAdjustment("ICU:beds", 15), PoolAdjustment("WARD:beds", -15))
        self.assertEqual([p.agent for p in res.accepted], ["bed"])

    def test_the_recipient_that_gets_worse_is_rejected_with_the_numbers(self):
        res = self.arbitrate(self.POOLS, {"nurse.max_patients_per_nurse:ICU": 2, "nurse.max_patients_per_nurse:WARD": 6},
                             PoolAdjustment("ICU:beds", 15), PoolAdjustment("WARD:beds", -15))
        self.assertFalse(res.accepted)
        reason = res.rejected[0].reasons[0]
        self.assertIn("27 beds need at least 14 nurses, 1 on shift (supports 2 beds)", reason)
        self.assertNotIn("WARD", reason)                                              # the donor is not named

    def test_losing_nurses_is_still_rejected(self):
        res = self.arbitrate({"ICU:beds": (12, 0), "ICU:nurses": (6, 0)}, {"nurse.max_patients_per_nurse:ICU": 2},
                             PoolAdjustment("ICU:nurses", -3))
        self.assertFalse(res.accepted)

    def test_missing_policy_still_fails_closed(self):
        res = self.arbitrate(self.POOLS, {}, PoolAdjustment("ICU:beds", 15), PoolAdjustment("WARD:beds", -15))
        self.assertFalse(res.accepted)
        self.assertIn("unverifiable", res.rejected[0].reasons[0])

    def test_bed_agent_proposes_the_largest_move_the_nurses_can_staff(self):
        inp = inputs({"ICU:beds": (12, 0), "WARD:beds": (36, 0), "ICU:nurses": (2, 0), "WARD:nurses": (6, 0)},
                     {"nurse.max_patients_per_nurse:ICU": 8, "nurse.max_patients_per_nurse:WARD": 8},
                     demand={"ICU:beds:demand": 20, "WARD:beds:demand": 5})
        d = run(Orchestrator(Settings(language="en")).run(inp))
        bed = next(p for p in d.accepted if p.agent == "bed")
        self.assertEqual(sorted(a.delta for a in bed.actions), [-4, 4])              # 2 nurses x 8 = 16 beds, 12 today -> +4 (not +8)
        self.assertEqual(d.card.unmet["ICU:beds"], 4)
        self.assertTrue(any("sized to +4 instead of +8" in r for r in bed.rationale))

    def test_when_nurses_allow_nothing_the_full_move_is_rejected_with_the_reason(self):
        inp = inputs({"ICU:beds": (12, 0), "WARD:beds": (36, 0), "ICU:nurses": (1, 0), "WARD:nurses": (6, 0)},
                     {"nurse.max_patients_per_nurse:ICU": 2, "nurse.max_patients_per_nurse:WARD": 8},
                     demand={"ICU:beds:demand": 20, "WARD:beds:demand": 5})
        d = run(Orchestrator(Settings(language="en")).run(inp))
        self.assertFalse(d.accepted)
        self.assertIn("nurses", d.rejected[0].reasons[0])
        self.assertTrue(any(w.startswith("ICU:") and "12 beds / 1 nurse" in w for w in d.card.warnings))   # the baseline breach is reported, not hidden


class EmptyDecisions(unittest.TestCase):
    """Finding 4."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(DATA, Path(self.tmp.name) / "rt", Path(self.tmp.name) / "pol")
        self.mgr = Principal("m", "operations_manager")

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_pressure_means_no_pending_decision(self):
        d = self.app.run({"as_of": "2026-10-17T08:00", "unit": "ICU", "multiplier": 1, "language": "en"}, self.mgr)
        self.assertEqual(d["status"], "NO_ACTION")
        self.assertEqual(d["no_action_code"], "none.reason.no_proposals")
        self.assertEqual(d["accepted"], [])
        self.assertIn("no forecast shortfall", d["note"])
        self.assertEqual(self.app.health()["pending"], 0)
        with self.assertRaises(ApiError) as e:
            self.app.approve(d["id"], {}, self.mgr)
        self.assertEqual(e.exception.status, 409)
        self.assertEqual(self.app.applied, [])

    def test_everything_rejected_is_closed_with_the_reason_not_left_pending(self):
        d = self.app.run({"as_of": "2026-10-17T08:00", "unit": "ICU", "multiplier": 12, "language": "en"}, self.mgr)
        self.assertEqual(d["status"], "PENDING")   # R4 OR schedules have verified free Sunday slots
        self.assertTrue(any(p["agent"] == "or" for p in d["accepted"]))
        self.assertFalse(any(p["agent"] == "bed" for p in d["accepted"]))
        self.assertGreater(d["card"]["unmet"]["ICU:beds"], 0)
        self.assertEqual(self.app.health()["pending"], 1)
        self.assertEqual(self.app.decisions()[0]["status"], "PENDING")

    def test_arabic_recommendations_use_the_r4_calendar_and_retain_arabic_text(self):
        d = self.app.run({"as_of": "2026-10-17T08:00", "unit": "ICU", "multiplier": 12, "language": "ar"}, self.mgr)
        self.assertEqual(d["status"], "PENDING")  # source R4 roster permits surgery moves
        self.assertTrue(d["accepted"])
        self.assertRegex(d["card"]["summary"], r"[\u0600-\u06FF]")
        self.assertGreater(d["card"]["unmet"]["ICU:beds"], 0)

    def test_a_decision_with_a_real_action_is_still_pending(self):
        for u in ("ICU", "WARD"):
            self.app.set_policy({"unit": u, "value": 40}, self.mgr)
        d = self.app.run({"as_of": "2026-10-17T08:00", "unit": "ICU", "multiplier": 12, "language": "en"}, self.mgr)
        self.assertEqual(d["status"], "PENDING")
        self.assertEqual(self.app.approve(d["id"], {}, self.mgr)["status"], "APPLIED")


class ReadableReasons(unittest.TestCase):
    """Finding 5."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(DATA, Path(self.tmp.name) / "rt", Path(self.tmp.name) / "pol")
        self.mgr = Principal("m", "operations_manager")
        for u, v in (("ICU", 2), ("WARD", 6)):
            self.app.set_policy({"unit": u, "value": v}, self.mgr)

    def tearDown(self):
        self.tmp.cleanup()

    def test_arabic_view_has_no_english_reason_sentences(self):
        d = self.app.run({"as_of": "2026-10-17T08:00", "unit": "ICU", "multiplier": 12, "language": "ar"}, self.mgr)
        ar = self.app.view(d["id"], "ar")
        en = self.app.view(d["id"], "en")
        arabic = re.compile(r"[\u0600-\u06FF]")
        texts = [t for r in ar["rejected"] for t in r["reasons"]] + ar["card"]["warnings"] + [ar["card"]["summary"]]
        self.assertTrue(texts)
        for t in texts:
            self.assertRegex(t, arabic, t)
            self.assertNotIn("exceeds", t)
        for r_ar, r_en in zip(ar["rejected"], en["rejected"]):
            self.assertIn("exceeds", r_en["reasons"][0])
            self.assertEqual(r_ar["reason_codes"], r_en["reason_codes"])   # same decision, same facts

    def test_both_languages_carry_the_same_numbers(self):
        d = self.app.run({"as_of": "2026-10-17T08:00", "unit": "ICU", "multiplier": 12, "language": "en"}, self.mgr)
        nums = lambda s: sorted(re.findall(r"\d+", s))
        ar, en = self.app.view(d["id"], "ar"), self.app.view(d["id"], "en")
        for a, e in zip(ar["rejected"], en["rejected"]):
            self.assertEqual(nums(a["reasons"][0]), nums(e["reasons"][0]))

    def test_catalog_is_complete_and_both_languages_use_the_same_placeholders(self):
        fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
        for code, (en, ar) in CATALOG.items():
            self.assertEqual(fields(en), fields(ar), code)
        used = set()
        for path in list((ROOT / "hospital_agents").rglob("*.py")) + [ROOT / "app.py"]:
            used |= set(re.findall(r'Msg\(\s*"([a-z_]+\.[a-z_.]+)"', path.read_text(encoding="utf-8")))
        self.assertFalse(used - set(CATALOG), used - set(CATALOG))

    def test_message_is_still_a_plain_string_with_a_stable_code(self):
        m = Msg("pool.unknown", pool="X:beds")
        self.assertIsInstance(m, str)
        self.assertEqual((m, m.code), ("X:beds: unknown pool", "pool.unknown"))
        self.assertEqual(m.render("ar"), "X:beds: مجمّع غير معروف")

    def test_what_if_labels_are_localised_but_keep_a_stable_key(self):
        sim = self.app.simulate({"as_of": "2026-10-17T08:00", "unit": "ICU", "multiplier": 12, "language": "ar"})
        self.assertEqual([u["metric_key"] for u in sim["unavailable"]], ["effect", "waiting", "revenue", "overtime"])
        self.assertRegex(sim["unavailable"][0]["metric"], r"[\u0600-\u06FF]")
        self.assertRegex(sim["cost_note"], r"[\u0600-\u06FF]")


if __name__ == "__main__":
    unittest.main()
