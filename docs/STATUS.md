# Phase status

Python 3.13.13 / Windows. Python 3.12 is not installed. Each `tests/*.py` file was run in its own pytest process. Changed files were rerun after fixes. No combined suite was used.

## Phase 0 — partial baseline

- Untouched baseline: `69a11c4`; Phase 0 commands/status: `4068c60`.
- Requirements note that the current runtime uses only the standard library; Makefile targets cover run, per-file test, schema, build-db, and report regeneration.
- The user-requested `pytest --timeout=120` command could not collect because `pytest-timeout` is unavailable. The same file was then run once with verbose unittest and a 120-second process limit: **24 passed in 58.003s**, no traceback. No Python 3.12 runtime was available.
- Browser test file: **7 skipped** because Playwright/Chromium is unavailable. See `docs/TODO.md` for the initial baseline note.

## Phase 1 — done

- Generated `db/schema.sql` for all **42 CSV tables**, their column types, primary/foreign keys, checks, and FK/date indexes. Added 42 `data_contracts/*.yaml` files and schema drift coverage.
- Built `runtime/hdt.sqlite`: **678,013 rows**; `foreign_key_check` reported **0** violations; `integrity_check` returned `ok`. Rebuilt successfully from the same source; row count remained 678,013.
- Regenerated `validation_report.json` from SQLite: **7 pass, 2 warn, 0 unresolved**. The two warnings include unapproved policy examples and uneven staff coverage.
- SQLite-backed TwinData preserves the string-dictionary access shape and lazily reads tables. Measured full `App` startup/RSS on this host: CSV **2.506s / 555.2 MB**; SQLite **1.483s / 75.3 MB**. TwinData-only: CSV **2.222s / 538.3 MB**; SQLite **0.838s / 60.0 MB**.
- Schema drift test: **3 passed**. Reconciliation and no-CSV-change record are in `docs/RECONCILIATION.md` and `docs/DATA_CHANGES.md`.

## Phase 2 — done

- `needs_icu_bed` now comes only from the surgery's planned ICU fields; historic ICU stays remain available for retrospective comparison and do not affect decisions.
- Clinic capacity counts doctors whose recorded shifts cover that hour. Future final surgery/appointment statuses no longer filter earlier replay bookings.
- OR booking rows carry case specialty. The pack has no provider/team IDs (only roster headcounts), so the hard constraint marks an OR move **UNVERIFIABLE** and refuses it; specialty mismatch also fails closed.
- Replay tests, including changes to post-`as_of` metrics/actuals: **5 passed**. Other affected files: `test_agents.py` **24 passed**, `test_data_pack.py` **16 passed**, `test_insights.py` **12 passed**, selected API lifecycle/safety cases **5 passed**, and `test_r4_decision_integration.py` **1 passed**.
- Full per-file verification found expectations that still assumed unverifiable OR changes would be accepted. Those tests now assert rejection. It also exposed a simulator count bug: clinic appointment moves were being labeled as postponed surgeries; only OR moves now count toward assumed bed relief. Updated affected test files passed on rerun.

## Per-file verification (Python 3.13 / Windows)

Every row is one separate pytest process. Durations are wall time and include process startup. `subtests` are unittest subtests reported within pytest.

| File | Result | Time |
| --- | --- | ---: |
| `test_agent_fixes.py` | 24 passed | 142.93s |
| `test_agents.py` | 24 passed | 2.35s |
| `test_agents_page.py` | 4 passed | 4.96s |
| `test_app.py` | 22 passed | 156.15s |
| `test_assistant.py` | 13 passed | 24.78s |
| `test_auth.py` | 6 passed | 8.04s |
| `test_browser.py` | 7 skipped (Playwright/Chromium unavailable) | 4.49s |
| `test_corpus.py` | 8 passed | 5.18s |
| `test_data_pack.py` | 16 passed | 47.98s |
| `test_frontend.py` | 3 passed, 1 skipped (legacy DOM harness) | 6.46s |
| `test_insights.py` | 12 passed | 24.22s |
| `test_llm.py` | 19 passed | 21.34s |
| `test_no_action_display.py` | 3 passed | 3.65s |
| `test_nurse_gate_and_plurals.py` | 17 passed, 4 subtests passed | 22.80s |
| `test_phase2_replay.py` | 5 passed | 17.02s |
| `test_policies.py` | 9 passed | 3.96s |
| `test_r4_decision_integration.py` | 1 passed | 15.25s |
| `test_r4_fix_and_routing.py` | 4 passed | 160.63s |
| `test_schema_drift.py` | 3 passed | 3.51s |
| `test_store.py` | 6 passed | 5.54s |
| `test_phase3_forecast.py` | 4 passed | 14.30s |

## Phase 3 — forecast — done

- Added a replay-safe, explainable weekday + linear-trend + annual/semi-annual seasonal regression. It trains only on complete observations before `as_of`; dashboards use the selected candidate or the weekday-mean fallback. Existing `forecast_results*` tables are not training inputs.
- Runs a 90-origin rolling backtest with 1–7 day leads. The trend-seasonal model is eligible for agent use only when both aggregate MAE and WAPE beat the naive same-weekday baseline. `db/evaluate_forecasts.py` replaces the old unverified evaluation rows with 144 baseline/model scores in `forecast_evaluation`, including aggregate (horizon 0) and each lead; `make build-db` regenerates them.
- Rebuild sequence verified: 42 tables / 678,013 rows, 0 FK violations, `integrity_check=ok`; evaluation wrote 144 rows; regenerated report is 7 pass / 2 warn / 0 unresolved.
- At the latest data date (2026-10-21 evaluation origin), 4/9 targets pass: ER arrivals, ER bed demand, ER wait, OR utilization. ER/ICU/WARD nurse demand, ICU bed demand, and ward bed demand fail or tie, so the corresponding agents abstain with a visible validation reason. No doctor-specific or resource-specific demand series exists; those agents abstain.
- Aggregate MAE/WAPE (weekday mean -> trend-seasonal): ER arrivals **9.1597 / 0.1297 -> 8.6706 / 0.1228**; ER beds **2.4888 / 0.3063 -> 2.4624 / 0.3030**; ER wait **23.8123 / 0.5149 -> 23.5795 / 0.5099**; OR utilization **14.8800 / 0.2290 -> 14.6900 / 0.2260**. ICU beds worsened (**1.7832 / 0.2119 -> 2.0712 / 0.2461**); Ward beds slightly worsened (**3.7728 / 0.1324 -> 3.7872 / 0.1329**).
- Forecasts expose the training source, selected model, rolling scores and abstention reason. Lower/upper interval values are null because calibration coverage has not been measured; no ± standard-deviation interval is shown. The 7-day ICU point peak changes across a 16-month origin span (0.7548 on 2025-06-23; 0.7829 on 2026-10-17). Its trend-seasonal candidate fails the backtest at the latest origin, so the displayed point is the weekday baseline and it is not sent to agents.
- Verification: `test_phase3_forecast.py` **4 passed**, `test_insights.py` **12 passed**, `test_data_pack.py` **16 passed**, `test_agents.py` **24 passed**, `test_agent_fixes.py` **24 passed**, `test_assistant.py` **13 passed**, `test_app.py` **22 passed**, `test_nurse_gate_and_plurals.py` **17 passed + 4 subtests**, `test_r4_decision_integration.py` **1 passed**, and `test_r4_fix_and_routing.py` **4 passed**. Each file ran in its own process.

## Phase 4 — scenario contract + simulation core — done

- Extended the backward-compatible `{unit, multiplier}` scenario with `as_of`, bounded `horizon`, typed interventions, data/policy versions, seed, and creator. Invalid types, ranges, known IDs, and past/out-of-horizon targets return HTTP 400. Scenario changes operate on copied immutable snapshots.
- Deterministic core emits before/after shortfall and deltas, computed donor/headroom hints, staffing changes, and clear rejection reasons. ICU/WARD (and nurse) weekday means are labeled **"assumption: unvalidated baseline forecast"**; doctor/resource demand abstains. Wait, revenue, and overtime remain unavailable without calibrated inputs.
- Bed additions remain explicitly assumed unless capacity/staffing/equipment authorization can be verified; current pack does not provide enough evidence. OR moves use the hard constraint gate: unverifiable teams refuse; compatible, open, free slots accept.
- Each run and its scenario/result events are persisted to `simulation_runs`/`simulation_events`; the replay endpoint reruns the stored parameters with the same seed. No source CSV is changed.
- The simulator UI now displays the weekday-mean estimate and staffing demand with the required assumption label; its text reflects per-run replay storage.
- Acceptance: staff, bed, OR, and combined scenario files passed **1/1, 1/1, 2/2, 3/3** respectively; combined covers monotonic x1.3/x12 demand, validation, and replay determinism. Existing API suite **22 passed**, with the simulation preview case rerun **1 passed**; frontend checks **3 passed, 1 skipped**. Python 3.13 / Windows.

## Remaining verification limits

- Python 3.12 behavior is unverified.
- Playwright/Chromium rendering remains unverified.
- OR moves will remain unavailable until source data provides a case provider or team assignment; the current roster only has counts.
- OR availability only covers 2026-10-21 through 2026-11-10. The schedule has no publication timestamp, so historical knowledge of that future roster is unavailable.
- Future booking rows with final `CANCELLED` / `RESCHEDULED` status have no effective timestamp; replay keeps the planned row as an **assumption** rather than leaking that later outcome into an earlier decision.
- The stated **1,236** actual OR turnover-gap count was not reproduced: adjacent actual-time pairs yield **1,262** when compared with the preceding surgery's turnover and **1,439** with the following surgery's turnover. See `docs/RECONCILIATION.md` for query definition and caveat.
- The obsolete root 23-table `schema.sql` was removed. Canonical generated schema is `db/schema.sql` with 42 tables; `validation_report.json` was regenerated from `runtime/hdt.sqlite` (7 pass, 2 warn, 0 unresolved).
