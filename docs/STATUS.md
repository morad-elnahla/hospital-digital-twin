# Phase status

Python 3.13.13 / Windows. Python 3.12 is not installed. Each `tests/*.py` file was run in its own pytest process. Changed files were rerun after fixes. No combined suite was used.

## Phase 0 — done

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
- Verification rerun: `tests/test_phase4_combined_scenario.py` **3 passed**; API decision lifecycle with an intervention and approval/apply/rollback plus invalid-intervention HTTP 400 **2 passed**.
- Same-as-of comparison command output (`python` calling `App.simulate`), `as_of=2026-10-17T08:00:00`: multiplier **1.3** → ICU shortfall **1**, **5 accepted actions**, **0 beds moved**, **0 reschedules**; multiplier **12** → shortfall **101**, **5 accepted actions**, **0 beds moved**, **0 reschedules**. The actions are clinic appointment changes; no ICU bed transfer or surgery move passed constraints. This is a 100-bed shortfall difference.
- Queue/wait estimate remains unavailable: the pack has daily aggregate arrivals and observed waits, but no ER service-completion rate or service-time distribution, number of parallel staffed service stations, or arrival/service observations at a matching hourly grain. Erlang-C utilization and waiting time therefore cannot be calibrated; daily average wait is not sufficient to infer those inputs.

## Phase 5 — policies, roles, LLM/RAG — done

- Added `policies/templates/er-nurse-ratio.md` with an empty `value` and `approved: false`. Manager entry saves an unapproved draft; only the explicit Approve action makes it available to hard constraints. No ratio value is supplied by the product.
- Added the `clinician` role: read/run permissions allow preview and scenario draft creation, while `decide` and `policy` remain operations-manager-only. Scenario drafts persist under `runtime/scenario_drafts.json` and are auditable.
- Detailed LLM validation returns each failed claim and reason, records `llm.unsupported` to audit, and uses deterministic template text on rejection. Mock failure-path coverage exercises assurance language, unsupported numbers, missing citations, malformed output, and the fallback.
- RAG evaluation uses 10 English and 10 Arabic questions at top-3: English **10/10 (100%)**, Arabic **0/10 (0%)**, overall **10/20 (50%)**. `docs/RAG_EVAL.md` and `docs/rag_eval_results.json` record the source-ID hit definition and result. Arabic retrieval is not supported by the current English-only corpus.
- Phase 5 verification: `test_auth.py` **6 passed**, `test_app.py` **25 passed** (rerun after correcting the ER-template expectation), `test_assistant.py` **14 passed**, `test_policies.py` **10 passed**, new role/policy tests **2 passed**, RAG eval **1 passed**, frontend **3 passed / 1 skipped**. `node --check` and Python compile checks passed.

## Phase 5b — relevance and multilingual retrieval — done

- Simulator labels the generic clinic appointments as “not related to this scenario,” excludes them from the scenario-applied snapshot, and reports scenario-relevant actions separately. ICU x12 returns `unresolved shortfall 101 beds: no verified action can cover it; needs manager/escalation` plus `what_would_help`. Regression test: **1 passed**.
- Arabic BM25 queries now receive reviewed-needed lexical English query expansion; retrieved source passages remain unchanged. The 20-query top-3 run improved Arabic from **0/10** to **10/10**, English stayed **10/10**. See [RAG_EVAL.md](RAG_EVAL.md). Combined scenario tests **3 passed**, frontend **3 passed / 1 skipped**, RAG eval **1 passed**.

## Phase 6 — source-based UI — done

- `lovable_src/hdt-ui` is the only UI source; `ui/` is generated by `scripts/package_app_py.mjs`. Backend serves the generated UI at `/` with SPA fallback and `/ui/*` assets. Browser rendering is not verified.

## Current Part A fixes — done

- Scenario decisions with a positive baseline residual and no verified action are now `ESCALATE`, not `NO_ACTION`; no-shortfall outcomes remain `NO_ACTION`. Escalations cannot be approved or applied. A manager can acknowledge/escalate with a required note, persisted in the decision and audit log. `/api/run`, `/api/simulate`, Agents and Scenario Lab expose the same outcome/residual fields.
- ICU ×1.3 and ×12 expected residuals are 1 and 101 beds. The escalation card displays the residual and `what_would_help` lines. English/Arabic UI labels cover the unvalidated baseline assumption, arrivals transition, and uncalibrated point estimate.
- Legacy `/static/*` paths are explicitly 404; current UI assets are served from `/ui/*`.

## Remaining verification limits

- Python 3.12 behavior is unverified.
- Playwright/Chromium rendering remains unverified.
- OR moves will remain unavailable until source data provides a case provider or team assignment; the current roster only has counts.
- OR availability only covers 2026-10-21 through 2026-11-10. The schedule has no publication timestamp, so historical knowledge of that future roster is unavailable.
- Future booking rows with final `CANCELLED` / `RESCHEDULED` status have no effective timestamp; replay keeps the planned row as an **assumption** rather than leaking that later outcome into an earlier decision.
- The stated **1,236** actual OR turnover-gap count was not reproduced: adjacent actual-time pairs yield **1,262** when compared with the preceding surgery's turnover and **1,439** with the following surgery's turnover. See `docs/RECONCILIATION.md` for query definition and caveat.
- The obsolete root 23-table `schema.sql` was removed. Canonical generated schema is `db/schema.sql` with 42 tables; `validation_report.json` was regenerated from `runtime/hdt.sqlite` (7 pass, 2 warn, 0 unresolved).

## Part A final verification (Python 3.13 / Windows, before FastAPI migration)

Every `tests/*.py` file ran in a separate `python -m pytest <file> -q` process with a 600-second per-file cap. `test_app.py` is below its 120-second target. The empty helper module is reported as skipped; browser and one legacy frontend harness test skip because browser rendering is unavailable.

| File | Result | Wall time |
| --- | --- | ---: |
| `phase4_helpers.py` | skipped (no tests collected) | 2.30s |
| `test_agent_fixes.py` | 24 passed | 130.57s |
| `test_agents_page.py` | 4 passed | 2.53s |
| `test_agents.py` | 24 passed | 2.07s |
| `test_app.py` | 26 passed | 111.82s |
| `test_assistant.py` | 14 passed | 20.39s |
| `test_auth.py` | 6 passed | 5.17s |
| `test_browser.py` | 7 skipped (Playwright/Chromium unavailable) | 1.92s |
| `test_contract_keys.py` | 1 passed | 26.33s |
| `test_corpus.py` | 8 passed | 2.25s |
| `test_data_pack.py` | 16 passed | 51.62s |
| `test_frontend.py` | 3 passed, 1 skipped | 2.05s |
| `test_insights.py` | 12 passed | 23.88s |
| `test_llm.py` | 19 passed | 18.51s |
| `test_no_action_display.py` | 3 passed | 1.95s |
| `test_nurse_gate_and_plurals.py` | 17 passed + 4 subtests | 24.26s |
| `test_phase2_replay.py` | 5 passed | 24.44s |
| `test_phase3_forecast.py` | 4 passed | 16.29s |
| `test_phase4_bed_scenario.py` | 1 passed | 5.56s |
| `test_phase4_combined_scenario.py` | 3 passed | 23.7s |
| `test_phase4_or_scenario.py` | 2 passed | 1.87s |
| `test_phase4_staff_scenario.py` | 1 passed | 5.83s |
| `test_phase5_rag_eval.py` | 1 passed | 2.24s |
| `test_phase5_roles_policy.py` | 2 passed | 5.19s |
| `test_phase5b_simulation_relevance.py` | 3 passed | 38.49s |
| `test_policies.py` | 10 passed | 1.99s |
| `test_r4_decision_integration.py` | 1 passed | 13.35s |
| `test_r4_fix_and_routing.py` | 4 passed | 161.95s |
| `test_scenario_relevance_filter.py` | 1 passed | 1.88s |
| `test_schema_drift.py` | 3 passed | 2.45s |
| `test_store.py` | 6 passed | 1.98s |

The app test profile previously exceeded its target (135–149s); main contributors were provider retry/backoff in a secret-redaction-only test and 500ms stdlib HTTP-server shutdown polling for each isolated case. The former now uses a mocked provider network error and the test server uses a 1ms poll interval. The staff insight route also reuses its capacity calculation instead of running it three times. Final `test_app.py`: 112.27s.

Lovable source suite: **40 passed** (6 Vitest files); Node **24.21.0** package build completed to `ui/`. Contract coverage is included in `test_contract_keys.py` (**1 passed**). Browser rendering, Docker execution, Python 3.12, and clinical validation remain unverified.

## Part B — FastAPI, operations, and consolidation — done

- `app.py` is the FastAPI/uvicorn transport and runtime entry point; the unchanged domain service is in `hospital_agents/service.py`. Existing route paths and response keys remain covered by `tests/contract_keys.json` and `test_contract_keys.py`. Request models feed generated OpenAPI at `/openapi.json`; JSON bodies from older clients without a content type remain accepted.
- Auth sessions persist as SHA-256 token hashes in `runtime/sessions.sqlite`; logout and expiry revoke them. Roles, CSP, approval revalidation (409), audit logging, sandbox apply/rollback, and response error shapes were retained. Read-only operations no longer share the service-wide mutation lock; the alert cache uses a separate lock.
- Structured request logs, environment configuration (`.env.example`), pinned FastAPI 0.135.1 / Pydantic 2.12.5 / uvicorn 0.41.0, non-root Docker image, app+Caddy compose, health check, CI workflow, and Windows/Unix run scripts are present. Docker and CI were not run.
- To meet `test_app.py`'s 120-second target without weakening tests, profiling found repeated replay-calendar construction was expensive. `TwinData.snapshot()` now reuses up to 32 immutable as-of snapshots. The HTTP test adapter also now joins its Uvicorn thread instead of waiting on a startup flag that never resets.
- Production lifespan smoke check built a fresh temporary SQLite database; `/` and `/openapi.json` returned 200, manager login returned 200, and the bearer session remained valid after constructing a second service instance.
- Rebuilt database: 42 tables, 678,013 rows, 0 FK violations, `integrity_check=ok`; forecast evaluation wrote 144 rows (4/9 targets pass); validation report is 7 pass / 2 warn / 0 unresolved. Lovable source tests: **40 passed** in 6 files.
- Baseline before FastAPI migration: simulate **7,361.3ms**, overview **794.0ms**, idle RSS **81.2MB**, after-request RSS **86.6MB**. After migration: simulate **8,607.0ms**, overview **1,009.6ms**, idle RSS **123.8MB**, after-request RSS **132.8MB**. Same Windows Python 3.13.13 process measurement; FastAPI/uvicorn add latency and memory.

Latest `tests/*.py` verification: one fresh pytest process per file, **600-second cap**, Python 3.13.13 / Windows. Every test file passed; `phase4_helpers.py` contains no tests. `test_browser.py` skips 7 cases because Playwright/Chromium are unavailable; `test_frontend.py` skips one legacy harness case. Test app now completes in **83.59s** (<120s). Wall times include process startup.

| File | Result | Time |
| --- | --- | ---: |
| `phase4_helpers.py` | no tests collected | 2.66s |
| `test_agent_fixes.py` | 24 passed | 141.89s |
| `test_agents.py` | 24 passed | 2.46s |
| `test_agents_page.py` | 4 passed | 2.50s |
| `test_app.py` | 26 passed | 86.00s |
| `test_assistant.py` | 14 passed | 24.30s |
| `test_auth.py` | 7 passed | 8.37s |
| `test_browser.py` | 7 skipped | 2.85s |
| `test_contract_keys.py` | 1 passed | 21.66s |
| `test_corpus.py` | 8 passed | 2.62s |
| `test_data_pack.py` | 16 passed | 48.69s |
| `test_frontend.py` | 3 passed, 1 skipped | 4.81s |
| `test_insights.py` | 12 passed | 21.36s |
| `test_llm.py` | 19 passed | 19.26s |
| `test_no_action_display.py` | 3 passed | 2.58s |
| `test_nurse_gate_and_plurals.py` | 17 passed, 4 subtests | 24.53s |
| `test_phase2_replay.py` | 5 passed | 22.23s |
| `test_phase3_forecast.py` | 4 passed | 17.74s |
| `test_phase4_bed_scenario.py` | 1 passed | 6.67s |
| `test_phase4_combined_scenario.py` | 3 passed | 21.17s |
| `test_phase4_or_scenario.py` | 2 passed | 2.10s |
| `test_phase4_staff_scenario.py` | 1 passed | 6.21s |
| `test_phase5_rag_eval.py` | 1 passed | 2.44s |
| `test_phase5_roles_policy.py` | 2 passed | 5.78s |
| `test_phase5b_simulation_relevance.py` | 3 passed | 32.64s |
| `test_policies.py` | 10 passed | 2.15s |
| `test_r4_decision_integration.py` | 1 passed | 11.83s |
| `test_r4_fix_and_routing.py` | 4 passed | 164.66s |
| `test_scenario_relevance_filter.py` | 1 passed | 2.40s |
| `test_schema_drift.py` | 3 passed | 2.90s |
| `test_store.py` | 6 passed | 2.11s |

Not verified: browser rendering, Docker build/run, GitHub Actions CI, Python 3.12 behavior, or clinical validity. `test_agent_fixes.py` and `test_r4_fix_and_routing.py` exceed 120 seconds but each passed under the 600-second file cap.
