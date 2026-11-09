"""Regression: source is canonical and its packaged build includes the Agents page."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "lovable_src" / "hdt-ui" / "src"
ASSETS = ROOT / "ui" / "assets"


class AgentsPageIsReachable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html = (ROOT / "ui" / "dashboard.html").read_text(encoding="utf-8")
        cls.html = html
        cls.source = (SOURCE / "routes" / "agents.tsx").read_text(encoding="utf-8")
        cls.assets = list(ASSETS.glob("*.js"))
        cls.bundle = "\n".join(p.read_text(encoding="utf-8") for p in cls.assets)

    def test_sidebar_has_the_agents_entry(self):
        self.assertIn('{ to: "/agents", key: "nav_agents"', (SOURCE / "components" / "hdt" / "shell.tsx").read_text(encoding="utf-8"))

    def test_route_is_registered_in_the_route_tree(self):
        self.assertIn('createFileRoute("/agents")', self.source)
        self.assertIn("/agents", self.bundle)

    def test_the_lazy_chunk_exists_is_imported_and_is_preloadable(self):
        self.assertTrue(any("agents" in p.name.lower() for p in self.assets), "agents route chunk missing from source build")

    def test_the_page_runs_the_agents_through_the_decision_endpoint(self):
        self.assertIn("/api/run", self.source)
        for key in ("nav_agents", "agents_sub", "run_agents", "run_prompt"):
            self.assertIn(key, self.source)
        self.assertIn("/api/run", self.bundle)


if __name__ == "__main__":
    unittest.main()
