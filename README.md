# Hospital Digital Twin (ZAWolf)

Phases 0–6 and the Phase 7–8 platform work are implemented. The API uses FastAPI/uvicorn with SQLite-persisted sessions. This is a synthetic-data operations prototype, not a live hospital system or a clinically validated decision aid.

The SQLite database has 42 CSV-backed tables. ICU/WARD bed and nurse forecast agents abstain because their trend-seasonal candidates did not beat the weekday-mean baseline. Scenario estimates may use weekday means only as an explicitly unvalidated assumption. Doctor and resource agents abstain because the data has no matching demand baseline. ER arrivals/wait and OR utilization passed the recorded backtest. OR moves also fail closed where provider/team identity cannot be verified. These results do not establish clinical validity.

## Windows quick start (PowerShell)

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 -m db.generate_schema
py -3.13 -m db.build_db
py -3.13 -m db.evaluate_forecasts
py -3.13 -m db.validate_data
py -3.13 app.py
```

Open `http://127.0.0.1:8000`; first-run credentials are printed to the server terminal. For a fresh UI build, in a second PowerShell window:

```powershell
cd lovable_src\hdt-ui
npm install
npm test
npm run build
node scripts/package_app_py.mjs ..\..\ui
```

Restart the server to load the rebuilt UI. Run the backend suite in separate processes with `py -3.13 scripts/run_tests.py`; run the UI suite with `npm test` from `lovable_src\hdt-ui`.

For a clean verification run from the project root, run the database commands above, then `py -3.13 scripts/run_tests.py`; in `lovable_src\hdt-ui`, run `npm test`, `npm run build`, and `node scripts/package_app_py.mjs ..\..\ui`.

Copy `.env.example` to `.env` to set passwords, paths, and optional provider settings. Use `py -3.13 app.py` to start the API and dashboard. OpenAPI docs are at `/docs` while the server is running.

## Verification limits

Browser rendering, Docker execution, GitHub Actions CI, and clinical validation are **not verified**. ICU/WARD bed and nurse forecasts abstain because the trend-seasonal candidates did not beat the weekday-mean baseline; doctor/resource demand abstains because no matching baseline exists. Scenario estimates may use weekday means only as an explicitly unvalidated assumption. See [docs/STATUS.md](docs/STATUS.md) for per-file results and known data limitations. The synthetic data and its derived reports must not be interpreted as real hospital performance.
