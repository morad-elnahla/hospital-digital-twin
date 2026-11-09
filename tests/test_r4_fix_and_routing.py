"""Fresh regression checks for verified OR-day capacity and Arabic data-question routing."""
import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app import App
import hospital_agents.auth as _auth
_auth.ITERATIONS = 2000  # local isolated test accounts only
from hospital_agents.auth import Principal
from hospital_agents.twin_data import TwinData

DATA = Path(__file__).resolve().parents[1] / 'data'
AS_OF = datetime(2026, 10, 15, 10)


class VerifiedCalendarRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.twin = TwinData(DATA)

    def test_closed_or_dates_never_have_capacity(self):
        slot_index = {s.key: s for s in self.twin.snapshot(AS_OF).slots if s.key.domain == 'OR'}
        for r in self.twin.t['or_availability']:
            from hospital_agents.contracts import SlotKey
            key = SlotKey('OR', r['or_id'], datetime.fromisoformat(r['date']))
            if r['availability_status'] != 'ROSTERED' or int(r['capacity_minutes']) == 0:
                self.assertNotIn(key, slot_index, f'closed roster entry created free slot: {key}')
            elif int(r['rostered_surgeons']) > 0 and int(r['rostered_anesthetists']) > 0:
                self.assertIn(key, slot_index)
                self.assertEqual(slot_index[key].capacity, int(r['capacity_minutes']))
                self.assertGreaterEqual(slot_index[key].booked, int(r['booked_minutes_with_turnover']))

    def test_r4_scheduled_moves_fail_closed_without_case_team_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(DATA, Path(tmp)/'rt', Path(tmp)/'pol')
            preview = app.simulate({'as_of': AS_OF.isoformat(), 'unit': 'ICU', 'multiplier': 1.3})
            self.assertEqual(preview['rescheduled_bookings'], 0)
            self.assertFalse(any(p['agent'] == 'or' for p in preview['decision']['accepted']))
            self.assertTrue(any('UNVERIFIABLE' in reason for item in preview['decision']['rejected']
                                if item['proposal']['agent'] == 'or' for reason in item['reasons']))
            d = app.run({'as_of': AS_OF.isoformat(), 'unit': 'ICU', 'multiplier': 1.3},
                        Principal('test', 'operations_manager'))
            dates = [a['to_slot']['start'][:10] for p in d['accepted'] if p['agent'] == 'or'
                     for a in p['actions'] if 'to_slot' in a]
            self.assertEqual(dates, [])
            self.assertTrue(all(datetime.fromisoformat(day).weekday() not in (4, 5) for day in dates))

    def test_calendar_is_bounded(self):
        self.assertEqual(self.twin.calendar_end, datetime(2026, 11, 11))
        self.assertTrue(all(s.key.start < self.twin.calendar_end for s in self.twin.snapshot(AS_OF).slots))


class AssistantRegression(unittest.TestCase):
    def test_surgery_count_with_request_for_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(DATA, Path(tmp)/'rt', Path(tmp)/'pol')
            out = app.assistant_ask({'message': 'كام عملية جراحية مسجلة في بيانات المستشفى؟ اذكر العدد ومصدره.',
                                     'language': 'ar', 'as_of': AS_OF.isoformat()}, Principal('test', 'viewer'))
            with (DATA / 'surgeries.csv').open(encoding='utf-8', newline='') as fd:
                actual_count = sum(1 for _ in csv.DictReader(fd))
            self.assertEqual(out['intent'], 'surgeries_count')
            self.assertIn(f'{actual_count:,}', out['answer'])
            self.assertEqual(out['evidence'][0]['table'], 'surgeries.csv')
            self.assertEqual(actual_count, 8953)


if __name__ == '__main__':
    unittest.main()
