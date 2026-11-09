# Phase status

Python 3.13.13 / Windows. Python 3.12 is not installed. Tests were run per file or as explicitly selected methods in one process; the full suite was not run.

## Phase 0 — partial baseline

- Untouched baseline: `69a11c4`; Phase 0 commands/status: `4068c60`.
- Requirements note that the current runtime uses only the standard library; Makefile targets cover run, per-file test, schema, build-db, and report regeneration.
- The user-requested `pytest --timeout=120` command could not collect because `pytest-timeout` is unavailable. The same file was then run once with verbose unittest and a 120-second process limit: **24 passed in 58.003s**, no traceback. No Python 3.12 runtime was available.
- Browser test file: **7 skipped** because Playwright/Chromium is unavailable. The initial per-file baseline was incomplete; see `docs/TODO.md`.

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
- `test_agent_fixes.py` was intentionally not rerun after Phase 2 because the request called for a single diagnostic run. Its recorded 24/24 result predates these changes. The full `test_app.py` file was not rerun after its assertions were adjusted; the 5 selected API cases passed.

## Remaining verification limits

- Python 3.12 behavior is unverified.
- Playwright/Chromium rendering remains unverified.
- OR moves will remain unavailable until source data provides a case provider or team assignment; the current roster only has counts.
- OR availability only covers 2026-10-21 through 2026-11-10. The schedule has no publication timestamp, so historical knowledge of that future roster is unavailable.
- Future booking rows with final `CANCELLED` / `RESCHEDULED` status have no effective timestamp; replay keeps the planned row as an **assumption** rather than leaking that later outcome into an earlier decision.
