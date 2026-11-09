"""Isolated real-backend tests for scenario relevance and decision persistence."""
import tempfile
import unittest
from pathlib import Path

from app import App, ApiError
from hospital_agents.auth import Principal
import hospital_agents.auth as auth
auth.ITERATIONS = 2000

ROOT = Path(__file__).resolve().parents[1]


class DecisionR4Integration(unittest.TestCase):
    def test_icu_escalation_excludes_clinic_moves_and_leaves_csv_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(ROOT / 'data', Path(tmp) / 'rt', Path(tmp) / 'pol')
            p = Principal('reviewer', 'operations_manager')
            data_files = sorted((ROOT / 'data').glob('*.csv'))
            before = {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in data_files}
            req = {'as_of': '2026-10-15T10:00', 'unit': 'ICU', 'multiplier': 12, 'language': 'ar'}
            preview = app.simulate(req)
            self.assertEqual(preview['rescheduled_bookings'], 0)  # clinic shifts do not count as postponed surgeries; ICU model failed validation
            self.assertEqual(len(app.decisions()), 0)
            d = app.run(req, p)
            self.assertEqual(d['status'], 'ESCALATE')
            self.assertEqual(d['accepted'], [])
            self.assertEqual(d['scenario_core']['bed_demand']['ICU']['residual_shortfall_beds'], 101)
            with self.assertRaises(ApiError) as exc:
                app.approve(d['id'], {}, p)
            self.assertEqual(exc.exception.status, 409)
            self.assertEqual(app.sandbox()['applied'], [])
            after = {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in data_files}
            self.assertEqual(before, after)

if __name__ == '__main__':
    unittest.main()
