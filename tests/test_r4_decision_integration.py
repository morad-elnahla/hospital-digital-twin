"""Isolated real-backend tests for R4 decision persistence, sandbox and rollback."""
import tempfile
import unittest
from pathlib import Path

from app import App, ApiError
from hospital_agents.auth import Principal
import hospital_agents.auth as auth
auth.ITERATIONS = 2000

ROOT = Path(__file__).resolve().parents[1]


class DecisionR4Integration(unittest.TestCase):
    def test_approve_rollback_and_no_csv_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(ROOT / 'data', Path(tmp) / 'rt', Path(tmp) / 'pol')
            p = Principal('reviewer', 'operations_manager')
            data_files = sorted((ROOT / 'data').glob('*.csv'))
            before = {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in data_files}
            req = {'as_of': '2026-10-15T10:00', 'unit': 'ICU', 'multiplier': 1.5, 'language': 'ar'}
            preview = app.simulate(req)
            self.assertEqual(preview['rescheduled_bookings'], 3)
            self.assertEqual(len(app.decisions()), 0)
            d = app.run(req, p)
            self.assertEqual(d['status'], 'PENDING')
            applied = app.approve(d['id'], {}, p)
            self.assertEqual(applied['status'], 'APPLIED')
            self.assertEqual(len(app.sandbox()['applied']), 1)
            result = app.rollback({}, p)
            self.assertEqual(result['status'], 'ROLLED_BACK')
            self.assertEqual(app.sandbox()['applied'], [])
            after = {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in data_files}
            self.assertEqual(before, after)

if __name__ == '__main__':
    unittest.main()
