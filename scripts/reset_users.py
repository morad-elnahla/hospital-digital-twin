"""Recreate the four local demo accounts from HDT_*_PASSWORD environment variables."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hospital_agents import llm  # noqa: E402
from hospital_agents.auth import Auth, AuthError  # noqa: E402


def main() -> None:
    llm.load_env(ROOT / ".env")
    runtime = Path(os.environ.get("HDT_RUNTIME_DIR", str(ROOT / "runtime")))
    runtime.mkdir(parents=True, exist_ok=True)
    users_file = runtime / "users.json"
    session_db = runtime / "sessions.sqlite"
    users_file.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(str(session_db) + suffix).unlink(missing_ok=True)
    session_db.unlink(missing_ok=True)

    auth = Auth(users_file, session_db=session_db)
    credentials = auth.initial_credentials or {}
    if set(credentials) != {"manager", "analyst", "viewer", "clinician"}:
        raise RuntimeError("user reset did not bootstrap all four roles")
    print("Recreated manager, analyst, viewer, and clinician accounts from HDT_*_PASSWORD settings.")
    print(f"Clinician password (shown once): {credentials['clinician']}")
    for name, password in credentials.items():
        token, principal = auth.login(name, password)
        auth.logout(token)
        try:
            auth.login(name, password + "-wrong")
        except AuthError as exc:
            if exc.status != 401:
                raise
        else:
            raise RuntimeError(f"wrong password unexpectedly worked for {name}")
        print(f"{name}: valid login verified; wrong password rejected (401); role={principal.role}")


if __name__ == "__main__":
    main()
