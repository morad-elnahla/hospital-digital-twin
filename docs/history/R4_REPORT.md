# Round 4 report

## Scope and change applied

Applied the requested calendar-boundary change only in `hospital_agents/twin_data.py`, plus one regression test in `tests/test_data_pack.py`. No agent logic, arbitration, constraints, safety checks, UI, or CSV values were changed by this Round 4 task.

The data maxima are planned surgery date 2026-11-10, appointment date 2026-11-10, and staff-shift start date 2026-11-10. The resulting exclusive calendar end is 2026-11-11T00:00:00, with calendar slots through 2026-11-10.

## Exact diff of the Round 4 patch

```diff
--- a/hospital_agents/twin_data.py
+++ b/hospital_agents/twin_data.py
@@
     @property
     def calendar_end(self) -> datetime:
         """Exclusive end of the known booking calendar: midnight after the last day of the pack."""
-        return datetime.combine(_dt(self.last_day).date() + timedelta(days=1), time.min)
+        planned_dates = (
+            [_dt(r["planned_start"]).date() for r in self.t["surgeries"]]
+            + [_dt(r["scheduled_start"]).date() for r in self.t["appointments"]]
+            + [_dt(r["shift_start"]).date() for r in self.t["staff_shifts"]]
+        )
+        return datetime.combine(max(planned_dates) + timedelta(days=1), time.min)
 
     def calendar(self, as_of: datetime) -> tuple[tuple[Slot, ...], tuple[Booking, ...]]:
-        end_day = _dt(self.last_day).date()
+        end_day = (self.calendar_end - timedelta(days=1)).date()
```

Regression test added:

```diff
--- a/tests/test_data_pack.py
+++ b/tests/test_data_pack.py
@@
     def test_bed_pools_match_the_bed_table(self):
         pools = td.pools(AS_OF)
         self.assertEqual((pools["ER:beds"].total, pools["ICU:beds"].total, pools["WARD:beds"].total), (12, 12, 36))
+
+    def test_calendar_end_tracks_latest_planned_date(self):
+        self.assertEqual(td.calendar_end, datetime(2026, 11, 11))
+        slots, _ = td.calendar(datetime(2026, 10, 15, 10))
+        self.assertTrue(any(slot.key.start.date() == datetime(2026, 11, 10).date() for slot in slots))
```

## Authorized `run_r4.py` output

`run_r4.py` was run exactly once from the project root with the requested redirection. The captured file contains the following complete output:

```text
load 6.9s | calendar_end = 2026-11-11 00:00:00
```

This verifies the calendar boundary. `run_r4.py` emitted no per-multiplier scenario rows, proposal details, agent notes, or OR-capacity arithmetic. Those values are therefore not reported or inferred here.

### Task 2 scenario-output status

| ICU multiplier | App.run decision/proposals/notes | OR-01 2026-10-23 booked vs available |
|---:|---|---|
| 1.0 | Not emitted by `run_r4.py` output | Not emitted |
| 1.3 | Not emitted by `run_r4.py` output | Not emitted |
| 1.5 | Not emitted by `run_r4.py` output | Not emitted |
| 2 | Not emitted by `run_r4.py` output | Not emitted |
| 3 | Not emitted by `run_r4.py` output | Not emitted |
| 12 | Not emitted by `run_r4.py` output | Not emitted |

Accordingly, questions (a), (b), and (c) cannot be answered from the authorized run output without another execution, which was explicitly not performed.

## Tests already run

Each requested test file was run in its own Python process; no test file was rerun after the user’s stop instruction.

| Test file | Result | Count | Failing/error test names |
|---|---|---:|---|
| `test_data_pack.py` | PASS | 16/16 | None |
| `test_agent_fixes.py` | PASS | 24/24 | None |
| `test_insights.py` | PASS | 12/12 | None |
| `test_nurse_gate_and_plurals.py` | FAIL | 13 passed, 3 failed, 1 error / 17 total | `test_approval_rechecks_the_gate_for_stored_decisions` — `AttributeError: App` has no `_gate_refusal`; `test_executive_summary_wording` — expected `1 action recommended`, received `1 action(s) recommended`; `test_no_placeholder_plurals_left_in_the_backend_sources` — `explain.py` contains `action(s)`; `test_icu_x12_on_19_oct_0800_moves_no_beds` — expected 2 ICU nurses, observed 3 |

The first three nurse-gate/plural failures are the known pre-existing issues recorded for this project. The ICU roster assertion is data-dependent against the current Round 4 roster.

## Open issues and limitations

The authorized runner confirms the corrected calendar end but does not print the requested six ICU scenario records. Therefore there is no verified result in this run for whether Bed or Staff proposals appear, the nurses-on-shift versus required-nurses comparison, or OR-01 capacity on 2026-10-23.

The nurse-gate/plural test file remains red for the three known implementation/wording issues and one current-roster expectation mismatch. Those issues were not modified under the task restrictions.

## Recommendation

Keep the calendar-boundary patch and its regression test. Before using the ICU stress conclusions operationally, update the approved reporting runner to emit the six per-multiplier App.run records and OR capacity arithmetic, then rerun it under the same controlled procedure. Do not infer proposal or staffing conclusions from the one-line output.
