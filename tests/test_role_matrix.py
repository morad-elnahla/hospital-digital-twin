"""Exercise every documented API operation for every role through FastAPI TestClient."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import app as A
import hospital_agents.auth as auth_module

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("viewer", "clinician", "analyst", "operations_manager")
PASSWORDS = {"viewer": "viewer-test-1", "clinician": "clinician-test-1",
             "analyst": "analyst-test-1", "operations_manager": "manager-test-1"}
USERS = {"viewer": "viewer", "clinician": "clinician", "analyst": "analyst", "operations_manager": "manager"}
ALLOWED = {
    "public": set(ROLES),
    "read": set(ROLES),
    "preview": {"clinician", "analyst", "operations_manager"},
    "run": {"analyst", "operations_manager"},
    "decide": {"operations_manager"},
    "policy": {"operations_manager"},
}


def permission_for(method: str, path: str) -> str:
    if path in ("/api/login", "/api/health"):
        return "public"
    if method == "post" and (path == "/api/rollback" or path == "/api/decisions/{decision_id}/{action}"):
        return "decide"
    if path == "/api/policies" and method == "post":
        return "policy"
    if path.startswith("/api/scenario-drafts") or path == "/api/simulate" or path.startswith("/api/simulations/"):
        return "preview"
    if path in ("/api/run", "/api/llm-test"):
        return "run"
    if method == "post" and path in {"/api/logout", "/api/assistant", "/api/assistant/reset"}:
        return "read"
    if method == "get":
        return "read"
    raise AssertionError(f"new state-changing OpenAPI operation needs an explicit permission mapping: {method} {path}")


class ApiRoleMatrix(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.iterations = mock.patch.object(auth_module, "ITERATIONS", 2000)
        self.iterations.start()
        self.env = mock.patch.dict(os.environ, {"HDT_HEALTH_TOKEN": "", "GROQ_API_KEY": ""})
        self.env.start()
        self.service = A.App(ROOT / "data", runtime=base / "runtime", policy_dir=base / "policies")
        for role, username in USERS.items():
            self.service.auth.create_user(username, PASSWORDS[role], role)
        self.web = A.create_app(self.service)
        self.client = TestClient(self.web)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.iterations.stop()
        self.temp.cleanup()

    def login(self, role: str) -> str:
        result = self.client.post("/api/login", json={"username": USERS[role], "password": PASSWORDS[role]})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()["token"]

    def route_body(self, method: str, path: str, role: str | None) -> dict | None:
        if method != "post":
            return None
        if path == "/api/login":
            if role is None:
                return {"username": "missing-user", "password": "wrong-password"}
            return {"username": USERS[role], "password": PASSWORDS[role]}
        if path in ("/api/run", "/api/simulate", "/api/scenario-drafts"):
            return {"unit": "ICU", "multiplier": 1, "language": "en",
                    "as_of": self.service.twin.default_as_of.isoformat()}
        if path == "/api/assistant":
            return {"message": "How many ICU beds?", "language": "en"}
        if path == "/api/policies":
            return {"unit": "ER", "value": 5}
        if path == "/api/decisions/{decision_id}/{action}":
            return {"note": "matrix probe", "reason": "matrix probe"}
        if path == "/api/rollback":
            return {"note": "matrix probe"}
        return {}

    def call_route(self, method: str, path: str, role: str | None = None):
        real_path = (path.replace("{decision_id}", "not-found")
                         .replace("{action}", "approve")
                         .replace("{simulation_id}", "not-found"))
        headers = {}
        if role is not None and path != "/api/login":
            headers["Authorization"] = "Bearer " + self.login(role)
        body = self.route_body(method, path, role)
        if body is None:
            return self.client.request(method.upper(), real_path, headers=headers)
        return self.client.request(method.upper(), real_path, json=body, headers=headers)

    def test_every_openapi_route_has_verified_status_for_each_role(self):
        schema = self.web.openapi()
        operations = sorted((method, path) for path, methods in schema["paths"].items()
                            for method in methods if method in {"get", "post", "put", "delete"})
        self.assertTrue(operations)
        matrix: dict[tuple[str, str], dict[str, int]] = {}
        for method, path in operations:
            statuses = {"unauthenticated": self.call_route(method, path).status_code}
            for role in ROLES:
                statuses[role] = self.call_route(method, path, role).status_code
            permission = permission_for(method, path)
            if permission == "public":
                self.assertEqual(statuses["unauthenticated"], 401 if path == "/api/login" else 200, path)
            else:
                self.assertEqual(statuses["unauthenticated"], 401, f"{method.upper()} {path} is missing auth")
            for role in ROLES:
                status = statuses[role]
                if role in ALLOWED[permission]:
                    self.assertNotIn(status, (401, 403), f"{role} unexpectedly blocked: {method.upper()} {path}")
                    self.assertLess(status, 500, f"{role} got server error: {method.upper()} {path}")
                else:
                    self.assertEqual(status, 403, f"{role} should be forbidden: {method.upper()} {path}")
            if method in {"post", "put", "delete"} and path != "/api/login":
                self.assertNotEqual(permission, "public", f"state-changing route lacks permission: {method} {path}")
                self.assertEqual(statuses["unauthenticated"], 401, f"state-changing route lacks auth: {method} {path}")
                if permission != "read":
                    self.assertEqual(statuses["viewer"], 403, f"viewer reached beyond read: {method} {path}")
            matrix[(method.upper(), path)] = statuses

        columns = ("unauthenticated", *ROLES)
        lines = ["# Verified API role matrix", "",
                 "Generated by `tests/test_role_matrix.py` from the live FastAPI OpenAPI schema. Each cell is the HTTP status from a request to that route.",
                 "Expected authorization: unauthenticated gets 401 except public health and login; disallowed roles get 403; allowed roles get a non-auth 2xx/4xx status (404 means the probe used a deliberately unknown record ID).", "",
                 "| Method | OpenAPI route | " + " | ".join(columns) + " |",
                 "|---|---|" + "---:|" * len(columns)]
        for (method, path), statuses in matrix.items():
            lines.append(f"| {method} | `{path}` | " + " | ".join(str(statuses[c]) for c in columns) + " |")
        lines.extend(["", "## Visible UI actions by role", "",
                      "| Role | Enabled actions | Disabled actions |",
                      "|---|---|---|",
                      "| viewer | Read pages and data; ask/reset own assistant history; sign out | Run agents, preview, save drafts, submit decisions, approve/reject/acknowledge, rollback, policy edits |",
                      "| clinician | Read; preview scenarios; save/review own drafts; sign out | Run agents, submit for approval, approve/reject/acknowledge, rollback, policy edits |",
                      "| analyst | Read; preview; save/review own drafts; run agents and submit decisions for manager review; sign out | Approve/reject/acknowledge, rollback, policy edits |",
                      "| operations_manager | All actions, including run, preview, draft review, decisions, rollback, and policy edits | None |",
                      "", "UI source audit: Simulator and Agents gate buttons from server-returned permissions; Decisions gates approve/reject/acknowledge/rollback; System gates policy edits. Browser rendering not verified.",
                      "", "Role spoofing, logout revocation, login lockout, and valid/wrong-password checks are covered by this file and `scripts/reset_users.py`.", ""])
        (ROOT / "docs" / "ROLE_MATRIX.md").write_text("\n".join(lines), encoding="utf-8")

    def test_role_is_server_side_and_logout_revokes_only_that_session(self):
        viewer_token = self.login("viewer")
        manager_token = self.login("operations_manager")
        forged_viewer = {"Authorization": f"Bearer {viewer_token}", "X-Role": "operations_manager",
                         "X-User-Role": "operations_manager"}
        self.assertEqual(self.client.get("/api/me", headers=forged_viewer).json()["role"], "viewer")
        self.assertEqual(self.client.post("/api/policies", json={"unit": "ER", "value": 5, "role": "operations_manager"},
                                          headers=forged_viewer).status_code, 403)
        self.assertEqual(self.client.post("/api/run", json={"unit": "ICU", "multiplier": 1, "role": "operations_manager"},
                                          headers=forged_viewer).status_code, 403)
        manager_headers = {"Authorization": f"Bearer {manager_token}", "X-Role": "viewer"}
        self.assertEqual(self.client.post("/api/policies", json={"unit": "ER", "value": 5, "role": "viewer"},
                                          headers=manager_headers).status_code, 200)
        self.assertEqual(self.client.post("/api/logout", headers={"Authorization": f"Bearer {viewer_token}"}).status_code, 200)
        self.assertEqual(self.client.get("/api/me", headers=forged_viewer).status_code, 401)
        self.assertEqual(self.client.get("/api/me", headers=manager_headers).json()["role"], "operations_manager")

    def test_login_lockout_after_five_wrong_passwords(self):
        for _ in range(5):
            self.assertEqual(self.client.post("/api/login", json={"username": "manager", "password": "wrong-password"}).status_code, 401)
        locked = self.client.post("/api/login", json={"username": "manager", "password": PASSWORDS["operations_manager"]})
        self.assertEqual(locked.status_code, 429)


if __name__ == "__main__":
    unittest.main()
