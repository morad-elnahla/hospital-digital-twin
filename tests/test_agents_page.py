"""Regression: the 'AI agents' page must stay reachable in the served (compiled) dashboard UI.

dashboard.html loads static/hdtui/assets/index-*.js. The sidebar, the route tree and the lazy chunk for
/agents must all exist there, and the chunk must call the endpoint that runs the seven agents.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "static" / "hdtui" / "assets"


class AgentsPageIsReachable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
        main = re.search(r'src="/static/hdtui/assets/(index-[\w\-]+\.js)"', html)
        assert main, "dashboard.html no longer loads the main bundle"
        cls.bundle = (ASSETS / main.group(1)).read_text(encoding="utf-8")

    def test_sidebar_has_the_agents_entry(self):
        self.assertRegex(self.bundle, r"\{to:`/agents`,key:`nav_agents`,icon:\w+\}")

    def test_route_is_registered_in_the_route_tree(self):
        self.assertIn("AgentsRoute:", self.bundle)
        self.assertIn("{id:`/agents`,path:`/agents`", self.bundle)

    def test_the_lazy_chunk_exists_is_imported_and_is_preloadable(self):
        chunk = re.search(r"import\(`\./(agents-[\w\-]+\.js)`\)", self.bundle)
        self.assertIsNotNone(chunk, "route does not import an agents chunk")
        self.assertTrue((ASSETS / chunk.group(1)).is_file(), chunk.group(1))
        self.assertIn(f"assets/{chunk.group(1)}", self.bundle)           # listed in the preload dependency map

    def test_the_page_runs_the_agents_through_the_decision_endpoint(self):
        chunk = re.search(r"import\(`\./(agents-[\w\-]+\.js)`\)", self.bundle).group(1)
        src = (ASSETS / chunk).read_text(encoding="utf-8")
        self.assertIn("/api/run", src)
        for key in ("nav_agents", "agents_sub", "run_agents", "run_prompt"):
            self.assertIn(f"`{key}`", src)
            self.assertRegex(self.bundle, key + r":`")                    # the text exists in the dictionary


if __name__ == "__main__":
    unittest.main()
