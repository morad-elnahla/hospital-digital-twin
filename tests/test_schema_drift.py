"""SQLite schema stays aligned with every source CSV and key declaration."""
import csv
import sqlite3
import unittest
from pathlib import Path

from db.generate_schema import DATA, PRIMARY_KEYS, ROOT

DB = ROOT / "runtime" / "hdt.sqlite"

class SchemaDrift(unittest.TestCase):
    def test_all_csv_headers_match_sqlite_columns(self):
        self.assertTrue(DB.exists(), "run make build-db before tests")
        with sqlite3.connect(DB) as conn:
            for path in sorted(DATA.glob("*.csv")):
                with path.open(encoding="utf-8-sig", newline="") as f:
                    expected = next(csv.reader(f))
                info = conn.execute(f'PRAGMA table_info("{path.stem}")').fetchall()
                self.assertEqual([row[1] for row in info], expected, path.stem)
                pk = [row[1] for row in sorted((r for r in info if r[5]), key=lambda r: r[5])]
                self.assertEqual(pk, list(PRIMARY_KEYS[path.stem]), path.stem)

    def test_declared_foreign_keys_hold_for_loaded_data(self):
        with sqlite3.connect(DB) as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_contract_file_exists_for_every_source_table(self):
        files = {p.stem for p in (ROOT / "data_contracts").glob("*.yaml")}
        self.assertEqual(files, {p.stem for p in DATA.glob("*.csv")})

if __name__ == "__main__":
    unittest.main()
