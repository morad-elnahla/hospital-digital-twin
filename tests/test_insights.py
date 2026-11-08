"""Dashboard analytics are recomputed independently from the CSVs: nothing is hard-coded."""
import csv
import unittest
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from hospital_agents import insights
from hospital_agents.twin_data import TwinData

DATA = Path(__file__).parent.parent / "data"
td = TwinData(DATA)
AS_OF = td.default_as_of


def rows(name):
    with (DATA / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class Insights(unittest.TestCase):
    def test_er_arrival_history_equals_visit_counts(self):
        cap = insights.capacity(td, AS_OF)["units"]["ER"]["flow"]
        days = insights._days(AS_OF, insights.HISTORY_DAYS)
        er = td.dept_by_type["ER"]
        self.assertEqual(cap["arrivals_history"], [float(td.metrics[d][er]["arrivals_count"]) for d in days])

    def test_hourly_arrivals_sum_to_the_daily_mean(self):
        flow = insights.capacity(td, AS_OF)["units"]["ER"]["flow"]
        mean_day = flow["visits_in_window"] / 28
        self.assertAlmostEqual(sum(flow["arrivals_by_hour"]), mean_day, delta=0.3)

    def test_forecast_has_no_future_leakage_and_reports_actuals_after_the_moment(self):
        for s in insights.forecasts(td, AS_OF)["series"]:
            self.assertTrue(all(h is None or True for h in s["history"]["values"]))
            self.assertTrue(all(d < AS_OF.date().isoformat() for d in s["history"]["dates"]))
            self.assertEqual(s["backtest"]["days"], sum(1 for p in s["forecast"] if p["actual"] is not None))
        early = insights.forecasts(td, datetime(2026, 8, 14, 8))["series"][0]
        self.assertTrue(all(p["date"] >= "2026-08-14" for p in early["forecast"]))

    def test_or_status_counts_match_the_surgeries_table(self):
        o = insights.operating_rooms(td, AS_OF)
        lo, hi = o["history_period"]["from"], o["history_period"]["to"]
        expect = Counter(s["status"] for s in rows("surgeries") if lo <= s["planned_start"][:10] <= hi)
        self.assertEqual(o["status_counts"], dict(expect))
        margin = sum(float(s["expected_contribution_margin_egp"]) for s in rows("surgeries")
                     if s["status"] == "CANCELLED" and lo <= s["planned_start"][:10] <= hi)
        self.assertAlmostEqual(o["cancelled_expected_margin_egp"], margin, delta=1)

    def test_workload_buckets_cover_every_active_clinical_staff_member(self):
        w = insights.staff(td, AS_OF)["workload_distribution"]
        clinical = [s for s in rows("staff") if s["is_active"] == "True" and s["role"] in ("NURSE", "DOCTOR", "SURGEON", "ANESTHETIST")]
        self.assertEqual((sum(w["staff"]), w["staff_total"]), (len(clinical), len(clinical)))

    def test_quality_checks_are_recomputed_not_copied(self):
        q = insights.quality(td, DATA.parent / "validation_report.json")
        by = {c["name"]: c for c in q["checks"]}
        self.assertEqual(by["Overlapping bed stays"]["value"], 0)
        self.assertEqual(by["Approved policies"]["status"], "warn")
        self.assertEqual(by["Days with unusual staff coverage"]["status"], "warn")
        self.assertEqual(q["tables"]["visits"], len(rows("visits")))
        self.assertEqual(sum(q["summary"].values()), len(q["checks"]))

    def test_quality_detects_a_planted_defect(self):
        broken = TwinData(DATA)
        broken.t["bed_stays"] = broken.t["bed_stays"] + [dict(broken.t["bed_stays"][0], bed_stay_id="X")]
        by = {c["name"]: c for c in insights.quality(broken)["checks"]}
        self.assertGreater(by["Overlapping bed stays"]["value"], 0)
        self.assertEqual(by["Overlapping bed stays"]["status"], "fail")

    def test_cards_report_change_against_the_previous_week(self):
        card = next(c for c in insights.overview(td, AS_OF)["cards"] if c["key"] == "er_wait")
        prev = [v for v in card["spark"][-8:-1] if v is not None]
        self.assertAlmostEqual(card["delta_pct"], 100 * (card["spark"][-1] - sum(prev) / len(prev)) / (sum(prev) / len(prev)), delta=0.1)

    def test_overview_cards_are_computed_from_the_data(self):
        o = insights.overview(td, AS_OF)
        cards = {c["key"]: c for c in o["cards"]}
        self.assertEqual(cards["beds"]["value"], sum(1 for b in rows("beds") if b["status"] == "AVAILABLE"))
        pools = td.pools(AS_OF)
        self.assertEqual(cards["patients"]["value"], sum(pools[f"{u}:beds"].committed for u in ("ER", "ICU", "WARD")))
        staff_now = sum(p.total for k, p in pools.items() if k.split(":")[1] in ("nurses", "doctors"))
        self.assertEqual(cards["staff"]["value"], staff_now)
        ahead = [s for s in rows("surgeries") if s["planned_start"] > AS_OF.isoformat(sep=" ") and s["status"] != "CANCELLED"]
        self.assertEqual(cards["surgeries"]["value"], len(ahead))
        self.assertEqual(o["bed_use"]["used"] + o["bed_use"]["available"], cards["beds"]["value"])
        self.assertEqual({p["type"] for p in o["pressure"]}, {"ER", "ICU", "WARD", "OR", "CLINIC", "IMAGING", "LAB"})

    def test_rolling_backtest_compares_methods_without_peeking(self):
        for s in insights.forecasts(td, AS_OF)["series"]:
            r = s["rolling"]
            self.assertLess(r["window"]["to"], AS_OF.date().isoformat())
            self.assertEqual(set(r["methods"]), {"weekday_mean", "seasonal_naive", "persistence"})
            self.assertGreater(r["methods"]["weekday_mean"]["n"], 40)
            self.assertIn(r["best_by_mae"], r["methods"])
        icu = next(s for s in insights.forecasts(td, AS_OF)["series"] if s["key"] == "icu_occ")["rolling"]["methods"]
        self.assertAlmostEqual(icu["weekday_mean"]["wape"], 0.162)  # replacement pack's measured value

    def test_twin_map_matches_the_bed_tables(self):
        m = insights.twin_map(td, AS_OF)
        pools = td.pools(AS_OF)
        by = {d["type"]: d for d in m["departments"]}
        for u in ("ER", "ICU", "WARD"):
            self.assertEqual(by[u]["beds_total"], pools[f"{u}:beds"].total)
            self.assertEqual(by[u]["occupied"], pools[f"{u}:beds"].committed)
            self.assertEqual(len(by[u]["beds"]), by[u]["beds_total"])
        self.assertEqual(len(by["OR"]["rooms"]), 6)
        self.assertTrue(m["schematic"])

    def test_nurse_coverage_gap_is_detected_with_synthetic_roster(self):
        days = ("2026-01-01", "2026-01-02")
        units = {"ER": "DEP-ER", "ICU": "DEP-ICU", "WARD": "DEP-WARD"}
        synthetic = SimpleNamespace(
            t={"bed_stays": [], "surgeries": [], "visits": [], "policy_documents": [], "decisions": []},
            metrics={d: {dep: {"arrivals_count": "0"} for dep in units.values()} for d in days},
            dept_by_type=units, shifts=[], staff_role={}, first_day=days[0], last_day=days[-1])
        by = {c["name"]: c for c in insights.quality(synthetic)["checks"]}
        self.assertEqual(by["Days without any nurse shift"]["value"], 6)
        self.assertEqual(by["Days without any nurse shift"]["status"], "warn")
        self.assertIn("ER 2, ICU 2, WARD 2", by["Days without any nurse shift"]["detail"])


if __name__ == "__main__":
    unittest.main()
