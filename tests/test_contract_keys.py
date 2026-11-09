"""API response-key contract for fields read by the source UI."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import hospital_agents.auth as auth  # noqa: E402

auth.ITERATIONS = 2000
CONTRACT = json.loads((ROOT / "tests" / "contract_keys.json").read_text(encoding="utf-8"))


def has_path(value, dotted):
    parts = dotted.replace("[]", ".*").strip(".").split(".")
    current = [value]
    for part in parts:
        next_values = []
        for item in current:
            if part == "*":
                if isinstance(item, list):
                    next_values.extend(item)
            elif isinstance(item, dict) and part in item:
                next_values.append(item[part])
        if not next_values:
            return False
        current = next_values
    return True


class UiResponseContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.server = A.make_server(ROOT / "data", 0, runtime=base / "runtime", policy_dir=base / "policies")
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.server.RequestHandlerClass.app.auth.create_user("contract-manager", "contract-pass-1", "operations_manager")
        self.token = None

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, method, path, body=None):
        data = None if method == "GET" else json.dumps(body or {}).encode()
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def assert_contract(self, method, endpoint, response):
        spec = CONTRACT[f"{method} {endpoint}"]
        for key in spec:
            self.assertTrue(has_path(response, key), f"{method} {endpoint} missing UI-read key {key}: {response}")

    def test_all_ui_endpoints_return_documented_keys(self):
        status, login = self.call("POST", "/api/login", {"username": "contract-manager", "password": "contract-pass-1"})
        self.assertEqual(status, 200)
        self.assert_contract("POST", "/api/login", login)
        self.token = login["token"]
        meta = self.call("GET", "/api/meta")[1]
        self.assert_contract("GET", "/api/meta", meta)
        self.assert_contract("GET", "/api/me", self.call("GET", "/api/me")[1])
        as_of = meta["default_as_of"]
        body = {"as_of": as_of, "unit": "ICU", "multiplier": 1.3, "horizon": 7, "seed": 11,
                "interventions": [{"type": "bed_change", "unit": "ICU", "delta": 1},
                                  {"type": "bed_change", "unit": "ICU", "delta": -100}],
                "language": "en", "scenario_lab": True}

        for endpoint in ("twin", "alerts", "overview", "capacity", "staff", "or", "forecasts"):
            response = self.call("GET", f"/api/{endpoint}?as_of={as_of}")[1]
            self.assert_contract("GET", f"/api/{endpoint}", response)
        for endpoint in ("status", "quality", "policies", "sandbox", "assistant", "knowledge"):
            path = f"/api/{endpoint}?q=policy" if endpoint == "knowledge" else f"/api/{endpoint}"
            self.assert_contract("GET", f"/api/{endpoint}", self.call("GET", path)[1])

        for unit in ("ICU", "WARD", "ER"):
            code, response = self.call("POST", "/api/policies", {"unit": unit, "value": 40 if unit != "ER" else 5})
            self.assertEqual(code, 200)
            self.assert_contract("POST", "/api/policies", response)
        code, response = self.call("POST", "/api/policies", {"unit": "ER", "approve": True})
        self.assertEqual(code, 200)
        self.assert_contract("GET", "/api/policies", response)

        code, preview = self.call("POST", "/api/simulate", body)
        self.assertEqual(code, 200, preview)
        self.assert_contract("POST", "/api/simulate", preview)
        code, draft = self.call("POST", "/api/scenario-drafts", body)
        self.assertEqual(code, 200, draft)
        self.assert_contract("POST", "/api/scenario-drafts", draft)
        self.assert_contract("GET", "/api/scenario-drafts", self.call("GET", "/api/scenario-drafts")[1])
        code, answer = self.call("POST", "/api/assistant", {"message": "How is ICU occupancy?", "as_of": as_of, "language": "en"})
        self.assertEqual(code, 200, answer)
        self.assert_contract("POST", "/api/assistant", answer)
        self.assert_contract("POST", "/api/assistant/reset", self.call("POST", "/api/assistant/reset", {})[1])

        code, decision = self.call("POST", "/api/run", body)
        self.assertEqual(code, 200, decision)
        self.assert_contract("POST", "/api/run", decision)
        self.assert_contract("GET", "/api/decisions", self.call("GET", "/api/decisions?lang=en")[1])
        code, detail = self.call("GET", f"/api/decisions/{decision['id']}?lang=en")
        self.assertEqual(code, 200)
        self.assert_contract("GET", "/api/decisions/<id>", detail)

        # Lifecycle routes return a status when actionable, or the backend's explicit error otherwise.
        for suffix, payload in (("approve", {"note": "contract"}), ("reject", {"reason": "contract"})):
            code, result = self.call("POST", f"/api/decisions/{decision['id']}/{suffix}", payload)
            if code == 200:
                self.assert_contract("POST", f"/api/decisions/<id>/{suffix}", result)
            else:
                self.assertIn("error", result)
        code, result = self.call("POST", "/api/rollback", {"note": "contract"})
        if code == 200:
            self.assert_contract("POST", "/api/rollback", result)
        else:
            self.assertIn("error", result)
        self.assert_contract("POST", "/api/logout", self.call("POST", "/api/logout", {})[1])


if __name__ == "__main__":
    unittest.main()
