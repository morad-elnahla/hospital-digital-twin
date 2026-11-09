"""Regenerate validation_report.json from the runtime SQLite database."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from hospital_agents.insights import quality
from hospital_agents.twin_data import TwinData
from db.generate_schema import ROOT

def generate(db_path: Path = ROOT / "runtime" / "hdt.sqlite", output: Path = ROOT / "validation_report.json") -> dict:
    td = TwinData(db_path)
    result = quality(td)
    row_counts = result["tables"]
    failures = [{"check": c["name"], "value": c["value"], "detail": c["detail"]}
                for c in result["checks"] if c["status"] == "fail"]
    warnings = [{"check": c["name"], "value": c["value"], "detail": c["detail"]}
                for c in result["checks"] if c["status"] == "warn"]
    report = {
        "report_type": "SQLite-backed synthetic data validation",
        "generated_on": date.today().isoformat(),
        "source": str(db_path),
        "table_count": len(row_counts),
        "visit_count": row_counts["visits"],
        "bed_stay_count": row_counts["bed_stays"],
        "surgery_count": row_counts["surgeries"],
        "days": len(td.metrics),
        "period": {"from": td.first_day, "to": td.last_day},
        "row_counts": row_counts,
        "checks": result["checks"],
        "summary": result["summary"],
        "unresolved_quality_checks": failures,
        "warnings": warnings,
        "evidence": {"confirmed_computation": {"source": str(db_path), "method": "read-only checks over loaded source rows"},
                     "model_estimate": [], "assumption": [], "unavailable": []},
        "limitations": ["Synthetic data only; no clinical validation",
                        "Source CSV values are loaded unchanged; this report applies documented counting conventions.",
                        "OR availability covers 2026-10-21 through 2026-11-10 only."],
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=ROOT / "runtime" / "hdt.sqlite")
    p.add_argument("--output", type=Path, default=ROOT / "validation_report.json")
    args = p.parse_args()
    report = generate(args.db, args.output)
    print(f"validation report written: {args.output}; {report['summary']}; unresolved={len(report['unresolved_quality_checks'])}")

if __name__ == "__main__":
    main()
