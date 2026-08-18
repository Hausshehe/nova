import unittest
from types import SimpleNamespace
from unittest.mock import patch

import nova_agent
from navigation.controller import NavigationResult, NavigationState
from navigation.path import OpenPathNavigator
from navigation.state import ObservationQuality, ScreenSnapshot


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

    def test_simple_open_does_not_use_loose_foreground_substring(self):
        current = {
            "success": True,
            "foreground_package": "com.google.android.apps.youtube.music",
            "state": {},
        }
        discovery = {
            "success": True,
            "verified": True,
            "packages": ["com.google.android.youtube"],
        }
        launch = {"success": True}
        with patch.object(nova_agent, "_observe_directly", return_value=current), patch.object(
            nova_agent,
            "execute_tool",
            side_effect=[discovery, launch],
        ) as execute:
            result = nova_agent._run_simple_open_goal("YouTube")

        self.assertFalse(result["success"])
        self.assertTrue(execute.called)
        self.assertEqual(execute.call_args_list[0].args[:2], ("find_android_app", "find_android_app"))

    def test_late_path_failure_retries_only_the_failed_target_from_checkpoint(self):
        settings = ScreenSnapshot(
            foreground_package="com.android.settings",
            observation_quality=ObservationQuality.VALID,
            visible_text=("Settings", "Apps"),
        )
        apps = ScreenSnapshot(
            foreground_package="com.android.settings",
            observation_quality=ObservationQuality.VALID,
            visible_text=("App Management", "Apps", "App list"),
        )
        app_list = ScreenSnapshot(
            foreground_package="com.android.settings",
            observation_quality=ObservationQuality.VALID,
            visible_text=("App list", "Assistant", "Screen time", "YouTube"),
        )

        class ScriptedController:
            def __init__(self):
                self.calls = []

            def navigate_target(self, target):
                self.calls.append(target)
                occurrence = self.calls.count(target)
                snapshots = {"Settings": settings, "Apps": apps, "YouTube": app_list}
                if target == "YouTube" and occurrence == 1:
                    return NavigationResult(
                        False,
                        False,
                        target,
                        NavigationState.FAILURE,
                        snapshot=app_list,
                        message="simulated late failure",
                    )
                return NavigationResult(
                    True,
                    True,
                    target,
                    NavigationState.SUCCESS,
                    snapshot=snapshots.get(target, app_list),
                    message="verified",
                )

        controller = ScriptedController()
        navigator = OpenPathNavigator(controller)
        with patch("navigation.path.observe_screen", return_value=app_list), patch(
            "navigation.path.find_android_app"
        ) as find_app:
            result = navigator.navigate("Open Settings and open Apps, then open YouTube")

        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertTrue(result.resumed_from_checkpoint)
        self.assertEqual(result.completed_targets, ["Settings", "Apps", "YouTube"])
        self.assertEqual(controller.calls, ["Settings", "Apps", "YouTube", "YouTube"])
        find_app.assert_not_called()


if __name__ == "__main__":
    unittest.main()