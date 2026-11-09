# Data changes

## Phase 1 SQLite build

- No source CSV values were edited.
- `python db/build_db.py` converts the CSV snapshot into derived `runtime/hdt.sqlite`; blank and `NaN` cells are represented as SQL `NULL`, boolean strings are stored as booleans, and numeric columns use numeric SQLite storage. The checked-in CSVs remain the source of truth.
- The one duplicate natural mapping key in `schema_mapping.csv` is preserved unchanged; its database primary key includes `definition` so both source rows are retained.
- Validation checks and conventions are documented in `docs/RECONCILIATION.md`.
- Removed the obsolete root `schema.sql` (23 tables); the generated canonical schema is `db/schema.sql` (42 tables).
- Phase 3 replaces derived `forecast_evaluation` rows from `daily_metrics` and `nurse_coverage_shift_detail` using 90 rolling-origin dates and 1–7 day leads. `forecast_results` and the old evaluation table values are not treated as trusted inputs. No source CSV values were edited.
