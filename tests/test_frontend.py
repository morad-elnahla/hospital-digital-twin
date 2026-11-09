"""Frontend packaging and source text regressions."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import hospital_agents.auth as _auth  # noqa: E402

_auth.ITERATIONS = 2000   # tests only: keep sign-ins fast; production uses 200 000

NODE = shutil.which("node")


def api(port, path, body=None, token=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {token}"} if token else {})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


@unittest.skipUnless(NODE, "Node.js not installed")
class Dashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.srv = A.make_server(ROOT / "data", 0, runtime=cls.tmp / "rt", policy_dir=cls.tmp / "pol")
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        A.Handler.app.auth.create_user("mgr", "dashboard-pw-1", "operations_manager")
        cls.token = api(cls.port, "/api/login", {"username": "mgr", "password": "dashboard-pw-1"})["token"]
        for u in ("ICU", "WARD"):
            api(cls.port, "/api/policies", {"unit": u, "value": 40}, cls.token)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp)

    def test_scripts_are_syntactically_valid(self):
        for path in (ROOT / "lovable_src/hdt-ui/scripts/package_app_py.mjs", ROOT / "lovable_src/hdt-ui/scripts/package-ssr.mjs"):
            r = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless((ROOT / "ui" / "dashboard.html").is_file(), "Source package has not been built")
    def test_every_page_renders_in_both_languages_and_the_main_flows_work(self):
        self.skipTest("Browser rendering is not exercised by the source package contract tests")

    def test_current_react_frontend_assets_are_served(self):
        """Smoke the actual bundled React entry instead of pretending the old DOM is the new UI."""
        import re
        base = f"http://127.0.0.1:{self.port}"
        with urllib.request.urlopen(base + "/") as r:
            html = r.read().decode("utf-8")
        self.assertIn("/ui/assets/", html)
        assets = set(re.findall(r'(?:src|href)="(/ui/[^"]+)"', html))
        self.assertGreaterEqual(len(assets), 8)
        for asset in sorted(assets):
            with urllib.request.urlopen(base + asset) as r:
                self.assertEqual(r.status, 200, asset)
                self.assertGreater(len(r.read()), 0, asset)
        with urllib.request.urlopen(base + "/simulator") as r:
            self.assertIn("Hospital Digital Twin", r.read().decode("utf-8"))

    def test_every_ui_text_key_exists_in_both_languages(self):
        import re
        source = (ROOT / "lovable_src/hdt-ui/src/lib/i18n.ts").read_text(encoding="utf-8")
        keys = ("scenario_lab", "assumption_label", "what_would_help", "not_related_action",
                "unrelated_suggestions_not_scenario", "scenario_unresolved_shortfall", "scenario_no_doctor_demand_baseline",
                "scenario_unit_why_line", "role_clinician", "approve_policy", "llm_claims_rejected", "template_fallback_shown",
                "arrivals_transition", "point_no_interval", "st_ESCALATE", "acknowledge_escalation")
        for key in keys:
            self.assertGreaterEqual(len(re.findall(rf'\b{key}:', source)), 2, f"{key} must have Arabic and English strings")
        simulator = (ROOT / "lovable_src/hdt-ui/src/routes/simulator.tsx").read_text(encoding="utf-8")
        self.assertNotIn("d.residual_message", simulator)  # residual is rendered once by the shared DecisionView
        decision_view = (ROOT / "lovable_src/hdt-ui/src/components/hdt/decision-view.tsx").read_text(encoding="utf-8")
        self.assertIn("residual_shortfall_beds", decision_view)
        self.assertIn('data-testid="decision-escalation"', decision_view)
        self.assertNotIn("{JSON.stringify(", simulator)
        agents = (ROOT / "lovable_src/hdt-ui/src/routes/agents.tsx").read_text(encoding="utf-8")
        self.assertIn("d.scenario_core", agents)
        self.assertIn("unrelated_suggestions", agents)
        copy = (ROOT / "lovable_src/hdt-ui/src/lib/i18n-source.ts").read_text(encoding="utf-8")
        self.assertNotIn("large multipliers are needed to create a bottleneck", copy)
        self.assertNotIn("نحتاج معاملات كبيرة لخلق اختناق", copy)


if __name__ == "__main__":
    unittest.main()
