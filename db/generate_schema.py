"""Generate a portable schema and compact contracts from the CSV headers and values."""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCHEMA = ROOT / "db" / "schema.sql"
CONTRACTS = ROOT / "data_contracts"
DATA_VERSION = "csv-snapshot-2026-11-09"

PRIMARY_KEYS = {
    "appointments": ("appointment_id",), "bed_status_events": ("event_id",),
    "bed_stays": ("bed_stay_id",), "beds": ("bed_id",), "calendar_days": ("date",),
    "calibration_params": ("group_type", "group_value", "parameter", "stat"),
    "cost_rates": ("cost_rate_id",), "daily_metrics": ("metric_id",),
    "data_quality_report": ("check_name",), "decisions": ("decision_id",),
    "departments": ("department_id",), "er_events": ("er_event_id",),
    "financial_daily": ("financial_id",), "financial_risk_daily": ("metric_date", "department_id"),
    "forecast_evaluation": ("run_group", "target", "horizon_days", "model_name"),
    "forecast_evaluation_aggregated": ("run_group", "target", "horizon_days", "model_name"),
    "forecast_results": ("forecast_id",), "forecast_results_aggregated": ("forecast_id",),
    "forecast_runs": ("run_id",), "future_booking_capacity_by_unit": ("date", "unit", "kind"),
    "future_booking_capacity_daily": ("date",),
    "hourly_forecast_evaluation": ("target_metric", "model_name"),
    "hourly_forecast_results": ("target_metric", "model_name", "forecast_for", "origin_time"),
    "hourly_metrics": ("hour_ts", "department_id"), "latent_events": ("date", "surge_type"),
    "nurse_coverage_by_unit_shift_weekday": ("period", "unit", "shift", "weekday"),
    "nurse_coverage_shift_detail": ("date", "unit", "shift"),
    "operating_rooms": ("or_id",), "or_availability": ("date", "or_id"),
    "patients": ("patient_id",), "policy_documents": ("document_id",),
    "resource_bookings": ("booking_id",), "resources": ("resource_id",), "rooms": ("room_id",),
    "schema_mapping": ("table", "column", "definition"), "simulation_events": ("simulation_event_id",),
    "simulation_runs": ("simulation_id",), "staff": ("staff_id",),
    "staff_assignments": ("assignment_id",), "staff_shifts": ("shift_id",),
    "surgeries": ("surgery_id",), "visits": ("visit_id",),
}

# (child table, child column, parent table, parent column)
FOREIGN_KEYS = (
    ("appointments", "patient_id", "patients", "patient_id"),
    ("appointments", "department_id", "departments", "department_id"),
    ("bed_status_events", "bed_id", "beds", "bed_id"),
    ("bed_stays", "visit_id", "visits", "visit_id"),
    ("bed_stays", "bed_id", "beds", "bed_id"),
    ("beds", "room_id", "rooms", "room_id"),
    ("cost_rates", "department_id", "departments", "department_id"),
    ("daily_metrics", "department_id", "departments", "department_id"),
    ("decisions", "simulation_id", "simulation_runs", "simulation_id"),
    ("er_events", "visit_id", "visits", "visit_id"),
    ("financial_daily", "department_id", "departments", "department_id"),
    ("financial_risk_daily", "department_id", "departments", "department_id"),
    ("forecast_results", "run_id", "forecast_runs", "run_id"),
    ("forecast_results_aggregated", "run_id", "forecast_runs", "run_id"),
    ("hourly_metrics", "department_id", "departments", "department_id"),
    ("nurse_coverage_shift_detail", "date", "calendar_days", "date"),
    ("operating_rooms", "department_id", "departments", "department_id"),
    ("or_availability", "or_id", "operating_rooms", "or_id"),
    ("policy_documents", "department_id", "departments", "department_id"),
    ("resource_bookings", "resource_id", "resources", "resource_id"),
    ("resource_bookings", "visit_id", "visits", "visit_id"),
    ("resources", "department_id", "departments", "department_id"),
    ("rooms", "department_id", "departments", "department_id"),
    ("simulation_events", "simulation_id", "simulation_runs", "simulation_id"),
    ("staff", "department_id", "departments", "department_id"),
    ("staff_assignments", "staff_id", "staff", "staff_id"),
    ("staff_assignments", "department_id", "departments", "department_id"),
    ("staff_shifts", "staff_id", "staff", "staff_id"),
    ("staff_shifts", "department_id", "departments", "department_id"),
    ("surgeries", "visit_id", "visits", "visit_id"),
    ("surgeries", "or_id", "operating_rooms", "or_id"),
    ("visits", "patient_id", "patients", "patient_id"),
)

KPI_MAP = {
    "appointments": [("scheduled appointments", "scheduled_start", "count by department_id and date; status filters the event" )],
    "bed_stays": [("bed occupancy", "start_time/end_time", "active interval per bed_id; end_time blank means still occupied")],
    "daily_metrics": [("reported arrivals", "arrivals_count", "department_id + metric_date; ER value is an aggregate snapshot"),
                       ("reported wait", "avg_wait_minutes/p90_wait_minutes", "department_id + metric_date; period summary")],
    "er_events": [("queue wait events", "queue_minutes", "event_time grouped by visit_id/event_type")],
    "financial_daily": [("daily financial totals", "revenue_egp/labor_cost_egp/supply_cost_egp/overtime_cost_egp", "department_id + metric_date")],
    "financial_risk_daily": [("daily risk estimates", "total_revenue_at_risk_egp", "department_id + metric_date; synthetic estimate")],
    "hourly_metrics": [("hourly flow", "arrivals/census/boarders/queue_len/avg_wait", "department_id + hour_ts")],
    "or_availability": [("OR capacity", "availability_status/capacity_minutes/free_minutes", "or_id + date + roster window"),
                        ("OR roster headcount", "rostered_surgeons/rostered_anesthetists", "counts only; no named provider/team assignment is present")],
    "resource_bookings": [("resource load", "quantity_reserved", "resource_id over booking_start..booking_end; exclude cancelled")],
    "staff_shifts": [("rostered staff", "staff_id/status", "department_id during shift_start..shift_end; exclude ABSENT")],
    "surgeries": [("surgery load", "planned_duration_minutes", "or_id + planned_start; planned schedule, not verified outcome"),
                  ("post-op ICU need", "icu_bed_required/post_op_destination", "planned case fields; historical stays are retrospective only"),
                  ("OR specialty compatibility", "specialty", "case field checked against operating_rooms.specialty; named provider/team IDs are unavailable")],
    "visits": [("visit arrivals", "arrival_time", "count by arrival date; can differ from daily_metrics convention")],
}

def q(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'

def quote_value(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"

def infer_types(path: Path, columns: list[str]) -> dict[str, str]:
    states = {c: {"bool": True, "int": True, "real": True, "date": True, "timestamp": True, "seen": False}
              for c in columns}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            for c in columns:
                value = (row.get(c) or "").strip()
                if not value or value.lower() in {"nan", "null", "none"}:
                    continue
                s = states[c]; s["seen"] = True
                s["bool"] &= value.lower() in {"true", "false", "0", "1"}
                s["int"] &= bool(re.fullmatch(r"[+-]?\d+", value))
                s["real"] &= _is_number(value)
                s["date"] &= bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
                s["timestamp"] &= bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T].+", value))
    out = {}
    for c in columns:
        n = c.lower(); s = states[c]
        if n.endswith("_json") or n in {"content", "details_json"}:
            kind = "TEXT"
        elif n == "date" or n.endswith("_date") or s["date"] and s["seen"]:
            kind = "DATE"
        elif n.endswith(("_time", "_at", "_ts", "_start", "_end")) or s["timestamp"] and s["seen"]:
            kind = "TIMESTAMP"
        elif n.startswith("is_") or n in {"approved", "coverage_ok", "in_interval"}:
            kind = "BOOLEAN"
        elif s["bool"] and s["seen"] and n.startswith(("is_", "has_")):
            kind = "BOOLEAN"
        elif s["seen"] and s["int"]:
            kind = "INTEGER"
        elif s["seen"] and s["real"]:
            kind = "NUMERIC"
        elif not s["seen"] and (n.endswith(("_minutes", "_hours", "_count", "_pct", "_egp", "_score"))
                                or n in {"n", "mae", "wape", "mape", "bias", "pinball_loss", "coverage_80", "skill_vs_naive", "random_seed"}):
            kind = "NUMERIC"
        else:
            kind = "TEXT"
        out[c] = kind
    return out

def check_constraints(table: str, columns: list[str], types: dict[str, str]) -> list[str]:
    checks = []
    for col, kind in types.items():
        name = col.lower()
        if kind == "BOOLEAN":
            checks.append(f"CHECK ({q(col)} IN (TRUE, FALSE))")
        elif name.endswith(("_rate", "_ratio")) and name not in {"hourly_cost_egp"}:
            checks.append(f"CHECK ({q(col)} IS NULL OR {q(col)} BETWEEN 0 AND 1)")
        elif any(token in name for token in ("duration", "wait_minutes", "length_of_stay", "boarding_minutes", "capacity_minutes", "free_minutes", "booked_minutes", "quantity_reserved", "synthetic_age", "daily_capacity_hours", "hourly_cost_egp")):
            checks.append(f"CHECK ({q(col)} IS NULL OR {q(col)} >= 0)")
    if {"start_time", "end_time"} <= set(columns):
        checks.append(f"CHECK ({q('end_time')} IS NULL OR {q('end_time')} >= {q('start_time')})")
    if {"shift_start", "shift_end"} <= set(columns):
        checks.append(f"CHECK ({q('shift_end')} > {q('shift_start')})")
    if {"assignment_start", "assignment_end"} <= set(columns):
        checks.append(f"CHECK ({q('assignment_end')} > {q('assignment_start')})")
    if table == "visits":
        checks.extend([f"CHECK ({q('acuity_level')} IS NULL OR {q('acuity_level')} BETWEEN 1 AND 5)",
                       f"CHECK ({q('departure_time')} IS NULL OR {q('departure_time')} >= {q('arrival_time')})"])
    if table == "departments":
        values = sorted({r["department_type"] for r in _rows(DATA / "departments.csv")})
        checks.append(f"CHECK ({q('department_type')} IN ({', '.join(quote_value(v) for v in values)}))")
    return checks

def _rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)

def generate() -> None:
    files = sorted(DATA.glob("*.csv"))
    if len(files) != 42:
        raise SystemExit(f"expected 42 CSV tables, found {len(files)}")
    schemas = {}
    for path in files:
        with path.open(encoding="utf-8-sig", newline="") as f:
            columns = next(csv.reader(f))
        if path.stem not in PRIMARY_KEYS:
            raise SystemExit(f"no primary key declared for {path.stem}")
        if not set(PRIMARY_KEYS[path.stem]) <= set(columns):
            raise SystemExit(f"invalid primary key for {path.stem}")
        seen_keys = set()
        for row in _rows(path):
            key = tuple(row.get(c, "") for c in PRIMARY_KEYS[path.stem])
            if any(not part for part in key) or key in seen_keys:
                raise SystemExit(f"null or duplicate primary key in {path.stem}: {key}")
            seen_keys.add(key)
        schemas[path.stem] = (columns, infer_types(path, columns))
    for child, col, parent, target in FOREIGN_KEYS:
        if child not in schemas or col not in schemas[child][0] or target not in schemas.get(parent, ([], {}))[0]:
            raise SystemExit(f"invalid foreign key {child}.{col} -> {parent}.{target}")

    lines = ["-- Generated by db/generate_schema.py from real data/*.csv headers and values.",
             "-- Synthetic operational sandbox only. Portable SQLite/PostgreSQL types; no clinical policies are inferred.", ""]
    index_specs = set()
    for table, (columns, types) in schemas.items():
        lines.append(f"CREATE TABLE {q(table)} (")
        defs = [f"  {q(c)} {types[c]}" for c in columns]
        pks = PRIMARY_KEYS[table]
        defs.append(f"  PRIMARY KEY ({', '.join(q(c) for c in pks)})")
        for child, col, parent, target in FOREIGN_KEYS:
            if child == table:
                defs.append(f"  FOREIGN KEY ({q(col)}) REFERENCES {q(parent)} ({q(target)})")
                index_specs.add((table, (col,)))
        defs.extend(f"  {check}" for check in check_constraints(table, columns, types))
        lines.append(",\n".join(defs))
        lines.append(");\n")
        for c, kind in types.items():
            if kind in {"DATE", "TIMESTAMP"}:
                index_specs.add((table, (c,)))
    for i, (table, cols) in enumerate(sorted(index_specs), 1):
        idx = f"idx_{table}_{'_'.join(cols)}"
        lines.append(f"CREATE INDEX {q(idx)} ON {q(table)} ({', '.join(q(c) for c in cols)});")
    SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA.write_text("\n".join(lines) + "\n", encoding="utf-8")

    CONTRACTS.mkdir(parents=True, exist_ok=True)
    relations = {}
    for child, col, parent, target in FOREIGN_KEYS:
        relations.setdefault(child, []).append(f"{col} -> {parent}.{target}")
    for table, (columns, _) in schemas.items():
        kpis = KPI_MAP.get(table, [])
        content = [f"table: {table}", f"data_version: {DATA_VERSION}", f"source: data/{table}.csv",
                   "primary_key: [" + ", ".join(PRIMARY_KEYS[table]) + "]", "relations:"]
        content += [f"  - {r}" for r in relations.get(table, [])] or ["  - none declared"]
        content += ["kpi_mappings:"]
        content += [f"  - name: {name}\n    columns: {cols}\n    mapping: {mapping}" for name, cols, mapping in kpis] or ["  - none directly consumed as a KPI"]
        content += ["columns: [" + ", ".join(columns) + "]", ""]
        (CONTRACTS / f"{table}.yaml").write_text("\n".join(content), encoding="utf-8")
    print(f"generated {SCHEMA.relative_to(ROOT)} and {len(schemas)} table contracts")

def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False

if __name__ == "__main__":
    generate()
