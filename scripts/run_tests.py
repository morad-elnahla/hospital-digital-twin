"""Run every tests/*.py file in its own Python process."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted((ROOT / "tests").glob("*.py"))
failed = False
for path in FILES:
    started = time.perf_counter()
    result = subprocess.run([sys.executable, "-m", "pytest", str(path), "-q"], cwd=ROOT,
                            env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
                            capture_output=True, text=True, timeout=600)
    elapsed = time.perf_counter() - started
    output = result.stdout + result.stderr
    summary = next((line.strip() for line in reversed(output.splitlines())
                    if any(word in line for word in ("passed", "failed", "skipped", "no tests ran"))), "no summary")
    status = "SKIP" if result.returncode == 5 else "PASS" if result.returncode == 0 else "FAIL"
    print(f"{path.name}\t{status}\t{elapsed:.2f}s\t{summary}", flush=True)
    if result.returncode not in (0, 5):
        print(output[-4000:], file=sys.stderr)
        failed = True
sys.exit(1 if failed else 0)
