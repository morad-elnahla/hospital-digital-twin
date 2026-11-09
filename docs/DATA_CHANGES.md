# Data changes

## Phase 1 SQLite build

- No source CSV values were edited.
- `python db/build_db.py` converts the CSV snapshot into derived `runtime/hdt.sqlite`; blank and `NaN` cells are represented as SQL `NULL`, boolean strings are stored as booleans, and numeric columns use numeric SQLite storage. The checked-in CSVs remain the source of truth.
- The one duplicate natural mapping key in `schema_mapping.csv` is preserved unchanged; its database primary key includes `definition` so both source rows are retained.
- Validation checks and conventions are documented in `docs/RECONCILIATION.md`.
