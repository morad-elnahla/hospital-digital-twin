"""Build runtime/hdt.sqlite atomically from the checked-in synthetic CSV pack."""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.generate_schema import DATA, FOREIGN_KEYS, PRIMARY_KEYS, ROOT, SCHEMA

NULLS = {"", "nan", "null", "none"}

def _insert_order() -> list[str]:
    tables = set(PRIMARY_KEYS)
    parents = {table: set() for table in tables}
    for child, _, parent, _ in FOREIGN_KEYS:
        if parent != child:
            parents[child].add(parent)
    order = []
    while parents:
        ready = sorted(t for t, deps in parents.items() if not deps)
        if not ready:
            raise RuntimeError(f"foreign-key cycle: {parents}")
        for t in ready:
            order.append(t)
            del parents[t]
        for deps in parents.values():
            deps.difference_update(ready)
    return order

def _value(value: str | None, kind: str):
    if value is None or value.strip().lower() in NULLS:
        return None
    value = value.strip()
    if kind == "BOOLEAN":
        v = value.lower()
        if v in {"true", "1"}:
            return 1
        if v in {"false", "0"}:
            return 0
        raise ValueError(f"invalid boolean {value!r}")
    if kind == "INTEGER":
        return int(value)
    if kind == "NUMERIC":
        n = float(value)
        return int(n) if n.is_integer() else n
    return value

def build(data_dir: Path = DATA, db_path: Path | None = None, schema_path: Path = SCHEMA) -> dict:
    data_dir, schema_path = Path(data_dir), Path(schema_path)
    target = Path(db_path) if db_path else ROOT / "runtime" / "hdt.sqlite"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="hdt-", suffix=".sqlite.tmp", dir=target.parent)
    os.close(fd)
    temp = Path(temp_name)
    counts = {}
    try:
        conn = sqlite3.connect(temp)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(schema_path.read_text(encoding="utf-8"))
            with conn:
                for table in _insert_order():
                    csv_path = data_dir / f"{table}.csv"
                    if not csv_path.exists():
                        raise FileNotFoundError(csv_path)
                    with csv_path.open(encoding="utf-8-sig", newline="") as f:
                        reader = csv.DictReader(f)
                        columns = reader.fieldnames or []
                        types = {row[1]: row[2].upper() for row in conn.execute(f'PRAGMA table_info("{table}")')}
                        quoted = ", ".join('"' + c.replace('"', '""') + '"' for c in columns)
                        marks = ", ".join("?" for _ in columns)
                        sql = f'INSERT INTO "{table}" ({quoted}) VALUES ({marks})'
                        batch = []
                        count = 0
                        for row in reader:
                            batch.append(tuple(_value(row.get(c), types[c]) for c in columns))
                            count += 1
                            if len(batch) >= 2000:
                                conn.executemany(sql, batch)
                                batch.clear()
                        if batch:
                            conn.executemany(sql, batch)
                        counts[table] = count
                bad_fk = conn.execute("PRAGMA foreign_key_check").fetchmany(10)
                if bad_fk:
                    raise RuntimeError(f"foreign-key violations (first 10): {bad_fk}")
                conn.execute("CREATE TABLE hdt_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                conn.executemany("INSERT INTO hdt_metadata VALUES (?, ?)", [
                    ("data_version", "csv-snapshot-2026-11-09"),
                    ("source", "data/*.csv"),
                    ("table_count", str(len(counts))),
                ])
        finally:
            conn.close()
        check = sqlite3.connect(temp)
        try:
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"integrity_check: {integrity}")
        finally:
            check.close()
        os.replace(temp, target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return {"path": str(target), "tables": len(counts), "rows": sum(counts.values()), "row_counts": counts}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--schema", type=Path, default=SCHEMA)
    args = parser.parse_args()
    result = build(args.data_dir, args.db_path, args.schema)
    print(f"built {result['tables']} tables / {result['rows']:,} rows at {result['path']}")
    print("foreign_key_check: 0 violations; integrity_check: ok")

if __name__ == "__main__":
    main()
