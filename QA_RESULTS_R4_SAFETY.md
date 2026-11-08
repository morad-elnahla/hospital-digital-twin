# Hospital Digital Twin — R4 Safety Patch & QA

**Date:** 2026-11-08  
**Source:** the user-supplied project ZIP, via `hospital_digital_twin_r4_verified_candidate.zip`.  
**Verdict:** **R4 backend regression candidate; not a complete R5 simulator or a clinical release.**

## Changes that affect the application

- `app.py`: decision **approval now revalidates every stored accepted proposal** against the current replay snapshot, known OR slots, and sourced nursing policies. Unsafe, unverifiable, tampered, or legacy actions fail closed with HTTP 409; nothing is applied to the sandbox. Tested with a stored ICU +15 / WARD -15 decision against a WARD with 29 occupied beds: a proposed remaining capacity of 21 is refused.
- `hospital_agents/explain.py`: correct English singular/plural wording in executive summaries (`1 action`, `1 minute`, `1 bed`); retains the strict LLM evidence-grounding and human approval warning.
- `validation_report.json`: regenerate the **snapshot report only** from current CSV row counts, preserving unresolved integrity failures. The old report was for a different 90-day dataset and disagreed with today's 546-day pack.
- `.env.example`: blank-key template for local configuration; **no real `.env`, users, tokens, or secrets in the archive**.
- Regression tests updated to reflect the verified R4 schedule, staff roster, nonfabricated bed headroom and OR turnover minutes. Stale assertions expecting the 2026-10-20 calendar end, 38 tables, zero accepted OR moves, or two ICU nurses on the 19th were replaced with evidence-based checks. Tests were not merely deleted to obtain a green count.

## Automated tests, executed in separate processes

- **191 PASSED, 0 FAILED, 8 SKIPPED** (199 cases; 22 isolated pytest groups).
- **7 skips:** legacy Playwright/browser tests unavailable in this environment.
- **1 skip:** legacy fake-DOM click-through for the *former* static dashboard, which does not exist in the current bundled React UI. Its replacement test checks that the current bundled React assets are served, **not** real browser rendering.
- App API lifecycle, authentication, roles, policy changes, R4 closed dates, OR capacity, assistant local query routing, arbitration, decision approval and rollback were tested.
- The full 22-group test summary was recorded in `hospital_final_qa_results.json` outside the project ZIP; the project remains free of log files.

## R4 independent manual harness

`python run_r4.py` exited 0. At `as_of=2026-10-15T10:00` ICU ×1.3, planned OR moves were to **2026-10-25 (Sunday)**, not the closed Fri/Sat. `calendar_end` was **2026-11-11 00:00** (exclusive).

## Data integrity — unresolved, not hidden

After regenerating the *matching* report from the current CSV files: **7 pass, 2 warning, 3 fail**.

- **311** overlapping planned operations by the existing interval check (investigate original booking/turnover semantics before editing data).
- **408** visits where recorded waiting exceeds length of stay.
- **390** dates on which ER arrivals differ between `daily_metrics` and `visits` under the existing counting convention.
- Synthetic example policies remain unapproved; missing ER nurse-ratio policy remains a configuration/safety blocker.
- All **42 CSV files are byte-for-byte unchanged** against the R4 candidate baseline.

## Still unbuilt / not verified

- R5 real What-if staffing reductions, equipment/floor-aware alternative proposals, physical bed increases, combined scenarios, and a calibrated patient-flow queue simulation.
- Real Groq completion and the previously observed `llm_unsupported` response; mock protocol tests pass, but the current strict validator can still fall back. Never package the API key.
- Live React UI click-through, mobile, RTL and 3D visual behaviour in Chromium (browser checks unavailable). The compiled frontend bundle was preserved unmodified.

## Run

```bash
python run_r4.py
python app.py
```

Open `http://127.0.0.1:8000`. This is a **synthetic-data R4 prototype**, not a hospital deployment.
