# Data reconciliation (SQLite build)

**Scope:** 42 checked-in synthetic CSV tables, data version `csv-snapshot-2026-11-09`. Source CSV files were not edited. Counts below are recomputed from `runtime/hdt.sqlite`; methods are in `hospital_agents/insights.py` and the SQLite builder is `db/build_db.py`.

| Prior check | Evidence and root cause | Check/report change |
| --- | --- | --- |
| 311 overlapping planned surgeries | The prior calculation applied `planned_start + planned_duration_minutes` to every historical row, including completed, delayed, and cancelled surgeries. The 311 adjacent planned-interval conflicts consist of 256 pairs involving only performed cases and 55 pairs involving a cancelled case. Completed/delayed cases have **0** overlaps using their recorded `actual_start`/`actual_end`; the currently `SCHEDULED` rows have **0** conflicts using planned intervals. | The quality check now uses actual intervals for performed cases, planned intervals for still-scheduled cases, and excludes cancelled cases. It reports 0. No CSV values were changed. |
| 408 waits longer than length of stay | All 408 records are `LEFT_WITHOUT_BEING_SEEN`. `wait_minutes` is integer minutes; `length_of_stay_hours` is rounded to hundredths of an hour. The apparent excess is at most 0.6 minute (36 seconds), consistent with the two stored precisions. | The consistency check allows a 1-minute representational tolerance and reports 0 beyond that tolerance. The tolerance is a data-precision comparison, not an operational or clinical threshold. No CSV values were changed. |
| 390 ER arrival-day mismatches | The 546-day `daily_metrics` window records non-elective ER arrivals (`WALK_IN` + `AMBULANCE`). `visits` also contains 7,960 `ELECTIVE` arrivals and extends 9 days earlier than the daily-metrics window. In the overlapping date range, filtering visits to `WALK_IN` + `AMBULANCE` yields **0** mismatches (36,044 total); counting every visit yields 390 mismatched dates. | The quality check now compares the same arrival convention over the daily-metrics dates and reports 0. No CSV values were changed. |

**Other integrity evidence:** database build loaded 678,013 rows; `PRAGMA foreign_key_check` returned 0 violations and `PRAGMA integrity_check` returned `ok`. `or_availability` only covers 2026-10-21 through 2026-11-10. Its surgeon/anesthetist fields are headcounts, not provider/team identifiers; case-to-team compatibility therefore remains unverifiable and blocks surgery moves.

## Evidence classes

- `confirmed_computation`: row counts, source-to-source reconciliation, recorded OR actual intervals, and database integrity checks, all with `runtime/hdt.sqlite` as source.
- `model_estimate`: none in this reconciliation.
- `assumption`: interpreting the rounded LOS / whole-minute discrepancy as a representation effect; the 1-minute comparison tolerance is explicitly limited to that check.
- `unavailable`: named surgery team/provider assignment; the pack has none. OR team match is not treated as passed.
