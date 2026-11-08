"""Regression tests.

1. Nurse-ratio safety gate: beds may only grow where nursing capacity is verified (>= 1 nurse on shift
   and beds / nurses within the sourced ratio). Zero nurses or missing data never passes.
   Reported case: 2026-10-19 08:00, ICU x12, 0 nurses on shift, the system accepted ICU +15.
2. English agreement in dynamic text: "1 bed", never "1 beds" / "nurse(s)".
"""
import re
import string
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app import ApiError, App
from hospital_agents import Settings
from hospital_agents.arbitration import Arbitrator
from hospital_agents.auth import Principal
from hospital_agents.contracts import Pool, PoolAdjustment, PolicyBundle, PolicyValue, Proposal, TwinSnapshot, make_id
from hospital_agents.explain import build_evidence
from hospital_agents.messages import CATALOG, Msg, count, plural

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
T0 = datetime(2026, 10, 19, 8)
MGR = Principal("m", "operations_manager")


def arbitrate(pools, policies, *acts):
    snap = TwinSnapshot(T0, "t", {k: Pool(k, *v) for k, v in pools.items()})
    prop = Proposal(make_id("bed", acts), "bed", "t", tuple(acts), ("r",))
    pol = PolicyBundle({k: PolicyValue(v, "src | text") for k, v in policies.items()})
    return Arbitrator(Settings()).resolve(snap, pol, [prop])


ICU2_WARD3 = {"nurse.max_patients_per_nurse:ICU": 2, "nurse.max_patients_per_nurse:WARD": 3}
MOVE_15 = (PoolAdjustment("ICU:beds", 15), PoolAdjustment("WARD:beds", -15))


class ZeroNurseGate(unittest.TestCase):
    def test_reported_case_zero_nurses_everywhere_is_rejected(self):
        res = arbitrate({"ICU:beds": (12, 0), "WARD:beds": (36, 14), "ICU:nurses": (0, 0), "WARD:nurses": (0, 0)},
                        ICU2_WARD3, *MOVE_15)
        self.assertFalse(res.accepted)
        reason = str(res.rejected[0].reasons[0])
        self.assertIn("27 beds need at least 14 nurses, 0 on shift (supports 0 beds)", reason)
        self.assertNotIn("WARD", reason)                         # the donor is not blamed

    def test_zero_nurses_in_the_recipient_only_is_rejected(self):
        res = arbitrate({"ICU:beds": (12, 0), "WARD:beds": (36, 0), "ICU:nurses": (0, 0), "WARD:nurses": (12, 0)},
                        ICU2_WARD3, *MOVE_15)
        self.assertFalse(res.accepted)

    def test_a_bed_increase_alone_with_no_nurses_is_rejected(self):
        res = arbitrate({"ICU:beds": (12, 0), "ICU:nurses": (0, 0)}, {"nurse.max_patients_per_nurse:ICU": 2},
                        PoolAdjustment("ICU:beds", 1))
        self.assertFalse(res.accepted)

    def test_unit_with_beds_and_no_nurses_is_never_compliant_even_with_a_huge_ratio(self):
        res = arbitrate({"ICU:beds": (12, 0), "ICU:nurses": (0, 0)}, {"nurse.max_patients_per_nurse:ICU": 1000},
                        PoolAdjustment("ICU:beds", 1))
        self.assertFalse(res.accepted)

    def test_missing_data_fails_closed(self):
        beds = {"ICU:beds": (12, 0), "WARD:beds": (36, 0)}
        for name, pools, pol in (
                ("no nurse pool", beds, ICU2_WARD3),
                ("no policy", {**beds, "ICU:nurses": (6, 0), "WARD:nurses": (12, 0)}, {}),
                ("zero ratio", {**beds, "ICU:nurses": (6, 0), "WARD:nurses": (12, 0)},
                 {"nurse.max_patients_per_nurse:ICU": 0, "nurse.max_patients_per_nurse:WARD": 3}),
                ("nan ratio", {**beds, "ICU:nurses": (6, 0), "WARD:nurses": (12, 0)},
                 {"nurse.max_patients_per_nurse:ICU": float("nan"), "nurse.max_patients_per_nurse:WARD": 3})):
            with self.subTest(name):
                res = arbitrate(pools, pol, *MOVE_15)
                self.assertFalse(res.accepted)
                self.assertIn("unverifiable", str(res.rejected[0].reasons[0]))

    def test_growth_that_improves_the_ratio_but_still_exceeds_it_is_rejected(self):
        # 12 beds / 2 nurses = 6 per nurse; +2 beds and +2 nurses = 3.5 per nurse: better, but still above 2.
        res = arbitrate({"ICU:beds": (12, 0), "ICU:nurses": (2, 0)}, {"nurse.max_patients_per_nurse:ICU": 2},
                        PoolAdjustment("ICU:beds", 2), PoolAdjustment("ICU:nurses", 2))
        self.assertFalse(res.accepted)

    def test_removing_nurses_is_rejected_even_when_none_are_left(self):
        res = arbitrate({"ICU:beds": (4, 0), "ICU:nurses": (2, 0)}, {"nurse.max_patients_per_nurse:ICU": 2},
                        PoolAdjustment("ICU:nurses", -2))
        self.assertFalse(res.accepted)

    def test_verified_capacity_still_passes(self):
        # ICU 8 beds / 4 nurses; +4 beds = 12 / 4 = 3 <= 3. WARD donates and stays within its own ratio.
        res = arbitrate({"ICU:beds": (8, 0), "ICU:nurses": (4, 0), "WARD:beds": (20, 0), "WARD:nurses": (10, 0)},
                        {"nurse.max_patients_per_nurse:ICU": 3, "nurse.max_patients_per_nurse:WARD": 3},
                        PoolAdjustment("ICU:beds", 4), PoolAdjustment("WARD:beds", -4))
        self.assertEqual(len(res.accepted), 1)

    def test_a_donor_that_strictly_improves_is_still_not_blamed(self):
        res = arbitrate({"ICU:beds": (12, 0), "ICU:nurses": (30, 0), "WARD:beds": (36, 0), "WARD:nurses": (2, 0)},
                        {"nurse.max_patients_per_nurse:ICU": 2, "nurse.max_patients_per_nurse:WARD": 6}, *MOVE_15)
        self.assertEqual(len(res.accepted), 1)


class ReportedScenarioEndToEnd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        pol = tmp / "pol"
        pol.mkdir()
        for unit, v in (("ICU", 2), ("WARD", 3)):
            (pol / f"p-{unit}.md").write_text(
                f"---\nid: p-{unit}\nsource: test\nkey: nurse.max_patients_per_nurse\nunit: {unit}\nvalue: {v}\n---\ntest\n",
                encoding="utf-8")
        self.app = App(DATA, tmp / "rt", pol)

    def tearDown(self):
        self._tmp.cleanup()

    def test_icu_x12_on_19_oct_0800_moves_no_beds(self):
        self.assertEqual(self.app.twin.pools(T0)["ICU:nurses"].total, 3)         # current R4 roster: three ICU nurses
        d = self.app.run({"as_of": "2026-10-19T08:00", "unit": "ICU", "multiplier": 12, "language": "en"}, MGR)
        moved = [a for p in d["accepted"] for a in p["actions"] if "pool" in a]
        self.assertEqual(moved, [])
        self.assertEqual(d["status"], "PENDING")  # OR postponement remains possible without adding beds
        self.assertTrue(any(p["agent"] == "or" for p in d["accepted"]))

    def _stored_unsafe_decision(self):
        """A PENDING record whose accepted set the old gate would have let through."""
        rec = {"id": "dec-legacy", "status": "PENDING", "as_of": T0.isoformat(),
               "scenario": {"unit": "ICU", "demand_multiplier": 12.0},
               "sandbox_rev": self.app.store.revision, "policy_fp": self.app.policy_fingerprint(), "seq": 1,
               "accepted": [{"id": "bed-legacy", "agent": "bed", "title": "t",
                             "actions": [{"pool": "ICU:beds", "delta": 15}, {"pool": "WARD:beds", "delta": -15}]}],
               "rejected": [], "language": "en"}
        self.app.store.records["dec-legacy"] = rec
        return rec

    def test_approval_rechecks_the_gate_for_stored_decisions(self):
        rec = self._stored_unsafe_decision()
        self.assertIn("WARD:beds", self.app._gate_refusal(rec))  # current roster: 29 occupied; 21 cannot be the donor total
        with self.assertRaises(ApiError) as cm:
            self.app.approve("dec-legacy", {}, MGR)
        self.assertEqual(cm.exception.status, 409)
        self.assertEqual(self.app.applied, [])                                    # nothing reached the sandbox
        self.assertEqual(self.app.store.records["dec-legacy"]["status"], "PENDING")


class PluralAgreement(unittest.TestCase):
    def test_helpers(self):
        self.assertEqual(count(1, "bed"), "1 bed")
        self.assertEqual(count(0, "bed"), "0 beds")
        self.assertEqual(count(12, "bed"), "12 beds")
        self.assertEqual(count(1.0, "nurse"), "1 nurse")
        self.assertEqual(count(1.5, "hour"), "1.5 hours")
        self.assertEqual(plural(1, "surgery", "surgeries"), "surgery")
        self.assertEqual(plural(2, "surgery", "surgeries"), "surgeries")

    def test_gate_messages_agree_with_the_numbers(self):
        one = Msg("nurse.exceeds", unit="ICU", beds=1, nurses=1, limit=1.0, required=1, supported=1, source="s")
        self.assertIn("1 bed / 1 nurse exceeds 1 patient per nurse", one)
        self.assertIn("1 bed needs at least 1 nurse, 1 on shift (supports 1 bed)", one)
        many = Msg("nurse.exceeds", unit="ICU", beds=27, nurses=0, limit=2.0, required=14, supported=0, source="s")
        self.assertIn("27 beds / 0 nurses exceeds 2 patients per nurse", many)
        self.assertIn("27 beds need at least 14 nurses, 0 on shift (supports 0 beds)", many)

    def test_other_dynamic_messages(self):
        self.assertIn("relieve 1 bed of demand", Msg("unv.relief", pool="ICU:beds", relief=1.0, unmet=3, unmet_assumed=2))
        self.assertIn("relieve 2 beds of demand", Msg("unv.relief", pool="ICU:beds", relief=2.0, unmet=3, unmet_assumed=1))
        self.assertIn("free 1 bed;", Msg("as.beds_per_procedure", beds=1.0))
        self.assertEqual(Msg("none.reason.all_rejected", n=1), "1 proposal was rejected by the hard constraints; nothing remains to apply.")
        self.assertTrue(Msg("none.reason.all_rejected", n=3).startswith("3 proposals were rejected"))
        self.assertTrue(Msg("unv.no_impact", n=1).startswith("1 accepted proposal has no"))
        self.assertTrue(Msg("unv.no_impact", n=2).startswith("2 accepted proposals have no"))
        self.assertIn("1 postponement is assumed to relieve 1 bed", Msg("sim.na_relief", n=1, relief=1.0))
        self.assertIn("2 postponements are assumed to relieve 2 beds", Msg("sim.na_relief", n=2, relief=2.0))
        self.assertIn("has 1 free minute of 60", Msg("or.verified_slot", room="OR-1", day="d", free=1, capacity=60, until="u"))
        cap = Msg("reb.nurse_cap", unit="ICU", nurses=1, ratio=1.0, max_beds=1, covered=1, wanted=3)
        self.assertIn("1 nurse on shift at 1 patient per nurse can staff at most 1 bed in ICU", cap)
        base = Msg("warn.baseline_ratio", unit="ICU", beds=12, nurses=1, limit=2.0)
        self.assertIn("12 beds / 1 nurse on shift already exceeds 2 patients per nurse", base)

    def test_executive_summary_wording(self):
        facts = {"decision_id": "d", "recommended_actions": ["a"], "rejected_count": 0, "critical_bottleneck": None,
                 "waiting_minutes_saved": 1.0, "confidence": None, "assumed_relief": {"ICU:beds": 1.0}}
        ev = build_evidence(facts, "en")
        self.assertIn("1 action recommended", ev["E1"])
        self.assertIn("1 minute of waiting", ev["E5"])
        self.assertIn("1 bed of demand", ev["E6b"])
        facts.update(recommended_actions=["a", "b"], waiting_minutes_saved=5.0, assumed_relief={"ICU:beds": 2.0})
        ev = build_evidence(facts, "en")
        self.assertIn("2 actions recommended", ev["E1"])
        self.assertIn("5 minutes of waiting", ev["E5"])
        self.assertIn("2 beds of demand", ev["E6b"])

    def test_no_english_template_pairs_one_with_a_plural_noun(self):
        """Render every catalog entry with every number set to 1: no '1 beds', no '(s)'."""
        bad = re.compile(r"\b1(?:\.0)? (?:beds|nurses|patients|minutes|proposals|postponements|actions|days|hours|decisions|bookings|doctors)\b"
                         r"|\(s\)")
        fmt = string.Formatter()
        for code, (en, _ar) in CATALOG.items():
            params = {}
            for _, field, spec, _ in fmt.parse(en):
                if field:
                    params[field] = 1 if (not spec or spec[-1] in "dgf" or "/" in spec) else "x"
            text = Msg(code, **params)
            self.assertIsNone(bad.search(text), f"{code}: {text}")

    def test_no_placeholder_plurals_left_in_the_backend_sources(self):
        placeholder = re.compile(r"\b(?:nurse|bed|proposal|postponement|action|decision|doctor|patient|minute|hour|day)\(s\)")
        for f in sorted((ROOT / "hospital_agents").rglob("*.py")):
            self.assertIsNone(placeholder.search(f.read_text(encoding="utf-8")), f.name)


if __name__ == "__main__":
    unittest.main()
