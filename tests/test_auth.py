import json
import os
import tempfile
import unittest
from pathlib import Path

from hospital_agents.auth import Auth, AuthError, Principal


class AuthUnit(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.now = 1000.0
        self.auth = Auth(self.dir / "users.json", clock=lambda: self.now)

    def test_first_run_creates_accounts_for_all_roles(self):
        creds = self.auth.initial_credentials
        self.assertEqual(set(creds), {"manager", "analyst", "viewer", "clinician"})
        self.assertEqual(len(set(creds.values())), 4)
        self.assertEqual({name: self.auth.login(name, password)[1].role for name, password in creds.items()},
                         {"manager": "operations_manager", "analyst": "analyst", "viewer": "viewer", "clinician": "clinician"})

    def test_passwords_are_stored_hashed_and_the_file_is_private(self):
        creds = self.auth.initial_credentials
        raw = (self.dir / "users.json").read_text()
        self.assertFalse(any(p in raw for p in creds.values()))
        if os.name == "posix":
            self.assertEqual((self.dir / "users.json").stat().st_mode & 0o077, 0)
        again = Auth(self.dir / "users.json")                    # accounts persist, nothing re-created
        self.assertIsNone(again.initial_credentials)
        self.assertIn("manager", json.loads(raw))

    def test_sessions_expire(self):
        self.auth.create_user("t", "long-enough-pw", "viewer")
        token, _ = self.auth.login("t", "long-enough-pw")
        self.assertEqual(self.auth.principal(token).username, "t")
        self.now += 9 * 3600
        self.assertIsNone(self.auth.principal(token))

    def test_permissions(self):
        for role, can in (("viewer", {"read"}), ("clinician", {"read", "preview"}),
                          ("analyst", {"read", "preview", "run"}),
                          ("operations_manager", {"read", "preview", "run", "decide", "policy"})):
            p = Principal("x", role)
            self.assertEqual({k for k in ("read", "preview", "run", "decide", "policy") if p.can(k)}, can)
        with self.assertRaises(AuthError):
            Auth.require(None, "read")
        with self.assertRaises(AuthError):
            Auth.require(Principal("x", "viewer"), "decide")

    def test_input_validation(self):
        for args in (("", "long-enough-pw", "viewer"), ("a", "short", "viewer"), ("a", "long-enough-pw", "root")):
            with self.assertRaises(ValueError):
                self.auth.create_user(*args)

    def test_unknown_user_costs_the_same_and_fails_the_same(self):
        with self.assertRaises(AuthError) as cm:
            self.auth.login("ghost", "whatever-pw")
        self.assertEqual(cm.exception.status, 401)

    def test_fifth_wrong_password_locks_the_account(self):
        self.auth.create_user("locked", "long-enough-pw", "analyst")
        for _ in range(5):
            with self.assertRaises(AuthError) as cm:
                self.auth.login("locked", "wrong-password")
            self.assertEqual(cm.exception.status, 401)
        with self.assertRaises(AuthError) as cm:
            self.auth.login("locked", "long-enough-pw")
        self.assertEqual(cm.exception.status, 429)
        self.now += 61
        self.assertEqual(self.auth.login("locked", "long-enough-pw")[1].role, "analyst")

    def test_sqlite_session_survives_auth_restart_and_logout_revokes_it(self):
        session_db = self.dir / "sessions.sqlite"
        first = Auth(self.dir / "persistent-users.json", session_db=session_db)
        first.create_user("persistent", "long-enough-pw", "clinician")
        token, principal = first.login("persistent", "long-enough-pw")
        self.assertEqual(principal.role, "clinician")

        restarted = Auth(self.dir / "persistent-users.json", session_db=session_db)
        self.assertEqual(restarted.principal(token), principal)
        restarted.logout(token)
        self.assertIsNone(Auth(self.dir / "persistent-users.json", session_db=session_db).principal(token))


if __name__ == "__main__":
    unittest.main()
