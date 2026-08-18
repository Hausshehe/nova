import unittest
from types import SimpleNamespace
from unittest.mock import patch

import nova_agent


class OpenPathIntegrationTests(unittest.TestCase):
    def test_three_stage_open_goal_uses_checkpoint_navigator(self):
        fake_result = SimpleNamespace(
            success=True,
            verified=True,
            message="All targets were reached and verified with checkpoints.",
            completed_targets=["Settings", "Apps", "YouTube"],
            targets=["Settings", "Apps", "YouTube"],
            failed_target="",
            checkpoints=3,
        )

        with patch.object(nova_agent, "OpenPathNavigator") as navigator_cls:
            navigator_cls.return_value.navigate.return_value = fake_result
            result = nova_agent.run_agent(
                "Open Settings and open Apps, then open YouTube"
            )

        navigator_cls.assert_called_once_with()
        navigator_cls.return_value.navigate.assert_called_once_with(
            "open Settings and open Apps and open YouTube"
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["completed_targets"], ["Settings", "Apps", "YouTube"])
        self.assertEqual(result["checkpoints"], 3)

    def test_non_path_goal_keeps_ai_planner_path(self):
        with patch.object(nova_agent, "call_ai", return_value={"content": "done"}) as call_ai:
            result = nova_agent.run_agent("Check the current battery level")

        call_ai.assert_called_once()
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
