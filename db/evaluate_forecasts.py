"""Replace unverified forecast-evaluation rows with Phase 3 rolling-origin scores."""
from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from datetime import datetime, time, timedelta
from pathlib import Path

from db.generate_schema import ROOT
from hospital_agents.forecasting import build, evaluation_rows
from hospital_agents.twin_data import TwinData


def evaluate(db_path: Path = ROOT / "runtime" / "hdt.sqlite") -> dict:
    td = TwinData(db_path)
    as_of = datetime.combine(datetime.fromisoformat(td.last_day).date() + timedelta(days=1), time(8))
    forecast_report = build(td, as_of)
    rows = evaluation_rows(td, as_of, forecast_report)
    columns = ("run_group", "target", "horizon_days", "model_name", "n", "mae", "wape",
               "mape_floor", "mape_floor_value", "bias", "pinball_loss", "coverage_80",
               "capped_day_share", "skill_vs_naive")
    values = [tuple(row.get(column) for column in columns) for row in rows]
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("DELETE FROM forecast_evaluation")
        placeholders = ",".join("?" for _ in columns)
        conn.executemany(f"INSERT INTO forecast_evaluation ({','.join(columns)}) VALUES ({placeholders})", values)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM forecast_evaluation").fetchone()[0]
    return {"as_of": as_of.isoformat(), "rows": count,
            "selections": {key: {"selected_model": item["selected_model"],
                                 "beats_baseline": item["beats_baseline"],
                                 "mae": item["rolling"]["overall"]}
                           for key, item in forecast_report.items()}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "runtime" / "hdt.sqlite")
    args = parser.parse_args()
    result = evaluate(args.db)
    selected = sum(item["beats_baseline"] for item in result["selections"].values())
    print(f"forecast evaluation written to {args.db}: {result['rows']} rows; "
          f"{selected}/{len(result['selections'])} targets passed the model gate; as_of={result['as_of']}")


if __name__ == "__main__":
    main()
