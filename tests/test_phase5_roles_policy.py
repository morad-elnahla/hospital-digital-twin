import asyncio
from pathlib import Path
import tempfile
import unittest

from app import App, ROOT, ApiError
from hospital_agents.auth import Principal
from hospital_agents.policies import FolderPolicyRetriever


class Phase5RolesAndPolicy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(ROOT / "data", Path(self.temp.name) / "runtime", Path(self.temp.name) / "policies")
        self.clinician = Principal("dr-demo", "clinician")
        self.manager = Principal("ops-demo", "operations_manager")

    def tearDown(self):
        self.temp.cleanup()

    def test_er_ratio_template_is_empty_and_unapproved_then_manager_can_enter_and_approve(self):
        template = ROOT / "policies" / "templates" / "er-nurse-ratio.md"
        self.assertRegex(template.read_text(encoding="utf-8"), r"(?m)^value:\s*$")
        row = next(r for r in self.app.policies()["nurse_ratio"] if r["unit"] == "ER")
        self.assertEqual((row["value"], row["approved"]), (None, False))

        self.app.set_policy({"unit": "ER", "value": 7}, self.manager)
        self.assertIsNone(asyncio.run(FolderPolicyRetriever(self.app.policy_dir).values(["ER"], self.app.twin.default_as_of))
                          .get("nurse.max_patients_per_nurse:ER"))
        self.app.set_policy({"unit": "ER", "approve": True}, self.manager)
        value = asyncio.run(FolderPolicyRetriever(self.app.policy_dir).values(["ER"], self.app.twin.default_as_of))
        self.assertEqual(value.get("nurse.max_patients_per_nurse:ER").value, 7)

    def test_clinician_can_save_own_scenario_draft_but_cannot_approve(self):
        draft = self.app.save_scenario_draft({"unit": "ICU", "multiplier": 1.3, "seed": 11}, self.clinician)
        self.assertEqual((draft["status"], draft["created_by"], draft["scenario"]["seed"]), ("DRAFT", "dr-demo", 11))
        self.assertEqual(self.app.list_scenario_drafts(self.clinician), [draft])
        with self.assertRaises(ApiError) as error:
            self.app.approve("unknown", {}, self.clinician)
        self.assertEqual(error.exception.status, 403)
        with self.assertRaises(ApiError) as error:
            self.app.save_scenario_draft({"unit": "ICU"}, Principal("view", "viewer"))
        self.assertEqual(error.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
