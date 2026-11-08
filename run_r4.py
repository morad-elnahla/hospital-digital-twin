"""Standalone ICU stress run. Put this file in the project root (next to app.py)
and run:  python run_r4.py
It uses a TEMP runtime folder, so the project's runtime/ and policies/ are untouched.
It disables the LLM key so nothing waits on the network."""
import os, sys, time, tempfile, json
from pathlib import Path

os.environ.pop("GROQ_API_KEY", None)          # offline: no network waits
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import App, Principal

ROOT = Path(__file__).resolve().parent
t0 = time.time()
with tempfile.TemporaryDirectory() as tmp:
    app = App(ROOT / "data", Path(tmp) / "rt", Path(tmp) / "pol")
    print(f"load {time.time()-t0:.1f}s | calendar_end = {app.twin.calendar_end}", flush=True)
    P = Principal("m", "operations_manager")
    for m in [1.0, 1.3, 1.5, 2, 3, 12]:
        t1 = time.time()
        d = app.run({"as_of": "2026-10-15T10:00", "unit": "ICU", "multiplier": m, "language": "en"}, P)
        print(f"\n=== ICU x{m}  ({time.time()-t1:.1f}s)  decision={d.get('decision') or d.get('status')}", flush=True)
        for p in d.get("accepted", []):
            for a in p.get("actions", []):
                print("  ACCEPT", p.get("agent"), json.dumps(a, default=str)[:260])
        for r in d.get("rejected", []):
            print("  REJECT", r.get("agent"), "|", "; ".join(r.get("reasons", []))[:260])
        for rep in d.get("reports", []):
            if rep["agent"] in ("bed", "staff", "or"):
                for n in rep.get("notes", [])[:3]:
                    print(f"  [{rep['agent']}] {n[:260]}")
print(f"\ntotal {time.time()-t0:.1f}s")
