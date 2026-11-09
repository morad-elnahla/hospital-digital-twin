"""Phase 3 forecast validation and as-of safety checks."""
import asyncio
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from hospital_agents import forecasting
from hospital_agents.agents.capacity import ResourceAgent, StaffAgent
from hospital_agents.config import Settings
from hospital_agents.twin_data import TwinData

DATA = Path(__file__).resolve().parents[1] / "data"
AS_OF = datetime(2026, 10, 17, 8)


class ForecastPhase3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = TwinData(DATA)
        cls.report = forecasting.build(cls.td, AS_OF)

    def test_models_are_selected_only_when_rolling_mae_and_wape_both_beat_naive(self):
        for target, result in self.report.items():
            metrics = result["rolling"]["overall"]
            expected = (metrics["weekday_mean"]["mae"] is not None
                        and metrics["weekday_trend_seasonal"]["mae"] < metrics["weekday_mean"]["mae"]
                        and metrics["weekday_trend_seasonal"]["wape"] < metrics["weekday_mean"]["wape"])
            self.assertEqual(result["beats_baseline"], expected, target)
            self.assertEqual(result["selected_model"],
                             "weekday_trend_seasonal" if expected else "weekday_mean", target)
            self.assertTrue(result["rolling"]["window"]["to"] < AS_OF.date().isoformat())
            self.assertTrue(all(point["lower"] is None and point["upper"] is None for point in result["points"]))

    def test_forecast_changes_across_as_of_dates(self):
        early = datetime(2025, 6, 23, 8)
        first = self.td.occupancy_forecast(early, "ICU")
        later = self.td.occupancy_forecast(AS_OF, "ICU")
        self.assertEqual(len(first), 7)
        self.assertEqual(len(later), 7)
        self.assertGreater(abs(max(p["predicted"] for p in first) - max(p["predicted"] for p in later)), 0.005)

    def test_agents_receive_only_backtested_demand_and_explain_abstention(self):
        inputs = self.td.inputs(AS_OF)
        for unit in ("ER", "ICU", "WARD"):
            expected = self.report[f"{unit}:occupancy"]["beats_baseline"]
            self.assertEqual(f"{unit}:beds:demand" in inputs.forecast.series, expected)
            nurse_expected = self.report[f"{unit}:nurses"]["beats_baseline"]
            self.assertEqual(f"{unit}:nurses:demand" in inputs.forecast.series, nurse_expected)
        staff = asyncio.run(StaffAgent().propose(inputs, Settings()))
        self.assertFalse(staff.proposals)
        self.assertTrue(any("rolling-origin validation" in note for note in staff.notes))
        resource = asyncio.run(ResourceAgent().propose(inputs, Settings()))
        self.assertTrue(any("resource-specific demand forecast" in note for note in resource.notes))

    def test_evaluation_rows_include_baseline_model_and_horizon_scores(self):
        rows = forecasting.evaluation_rows(self.td, datetime.fromisoformat(self.td.last_day) + timedelta(days=1))
        self.assertEqual(len(rows), 9 * 8 * 2)
        self.assertEqual({r["model_name"] for r in rows}, {"weekday_mean", "weekday_trend_seasonal"})
        self.assertEqual({r["horizon_days"] for r in rows}, set(range(8)))
        self.assertTrue(all(r["n"] >= 0 for r in rows))


if __name__ == "__main__":
    unittest.main()
