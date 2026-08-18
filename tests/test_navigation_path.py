import unittest
from unittest.mock import patch

from navigation.controller import NavigationResult, NavigationState
from navigation.path import OpenPathNavigator
from navigation.state import ObservationQuality, ScreenSnapshot
from navigation.verifier import VerificationResult


class FakeController:
    def __init__(self):
        self.calls = []

    def navigate_target(self, target, *, initial_direction):
        self.calls.append((target, initial_direction))
        return NavigationResult(
            False,
            False,
            target,
            NavigationState.FAILURE,
            snapshot=ScreenSnapshot(
                foreground_package="com.android.settings",
                observation_quality=ObservationQuality.VALID,
                visible_text=("Apps",),
            ),
            message="simulated failure",
        )


class NavigationPathTests(unittest.TestCase):
    def test_later_steps_cannot_bypass_ui_with_direct_app_launch(self):
        controller = FakeController()
        navigator = OpenPathNavigator(controller)

        with patch("navigation.path.find_android_app", return_value={"packages": []}) as find_app:
            result = navigator.navigate("Open Settings and open Apps, then open YouTube")

        self.assertFalse(result.success)
        self.assertEqual(result.failed_target, "Settings")
        find_app.assert_called_once_with("Settings")
        self.assertEqual(controller.calls, [("Settings", "down")])

    def test_single_app_step_may_use_package_fallback(self):
        controller = FakeController()
        navigator = OpenPathNavigator(controller)
        before = ScreenSnapshot(
            foreground_package="com.android.settings",
            observation_quality=ObservationQuality.VALID,
            visible_text=("Settings",),
        )
        verification = VerificationResult(
            success=False,
            snapshot=before,
            reason="simulated verification failure",
        )

        with patch("navigation.path.find_android_app", return_value={"packages": ["com.example.reader"]}), patch(
            "navigation.path.launch_android_app", return_value={"success": True}
        ) as launch, patch("navigation.path.observe_screen", return_value=before), patch(
            "navigation.path.verify_transition", return_value=verification
        ):
            result = navigator.navigate("Open Reader")

        self.assertFalse(result.success)
        self.assertEqual(result.failed_target, "Reader")
        launch.assert_called_once_with("com.example.reader")

    def test_later_step_retries_from_last_verified_checkpoint(self):
        checkpoint = ScreenSnapshot(
            foreground_package="com.android.settings",
            observation_quality=ObservationQuality.VALID,
            visible_text=("App Management", "Apps", "App list"),
        )
        app_list = ScreenSnapshot(
            foreground_package="com.android.settings",
            observation_quality=ObservationQuality.VALID,
            visible_text=("App list", "Assistant", "Screen time"),
        )

        class ResumeController:
            def __init__(self):
                self.calls = []

            def navigate_target(self, target, *, initial_direction):
                self.calls.append((target, initial_direction))
                if target == "Settings":
                    return NavigationResult(
                        True,
                        True,
                        target,
                        NavigationState.SUCCESS,
                        snapshot=checkpoint,
                        message="settings verified",
                    )
                if sum(1 for called_target, _ in self.calls if called_target == "Apps") == 1:
                    return NavigationResult(
                        False,
                        False,
                        target,
                        NavigationState.FAILURE,
                        snapshot=checkpoint,
                        message="simulated late failure",
                    )
                return NavigationResult(
                    True,
                    True,
                    target,
                    NavigationState.SUCCESS,
                    snapshot=app_list,
                    message="apps verified on checkpoint retry",
                )

        controller = ResumeController()
        navigator = OpenPathNavigator(controller)

        with patch("navigation.path.observe_screen", return_value=checkpoint):
            result = navigator.navigate("Open Settings and open Apps")

        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertTrue(result.resumed_from_checkpoint)
        self.assertEqual(result.completed_targets, ["Settings", "Apps"])
        self.assertEqual(controller.calls, [("Settings", "down"), ("Apps", "down"), ("Apps", "down")])
        self.assertEqual(result.checkpoints, 2)

    def test_checkpoint_resume_requires_matching_screen(self):
        checkpoint = ScreenSnapshot(
            foreground_package="com.android.settings",
            observation_quality=ObservationQuality.VALID,
            visible_text=("App Management", "Apps", "App list"),
        )
        different_screen = ScreenSnapshot(
            foreground_package="com.android.settings",
            observation_quality=ObservationQuality.VALID,
            visible_text=("Wi-Fi", "Network", "Internet"),
        )

        class ResumeController:
            def __init__(self):
                self.calls = []

            def navigate_target(self, target, *, initial_direction):
                self.calls.append((target, initial_direction))
                if target == "Settings":
                    return NavigationResult(True, True, target, NavigationState.SUCCESS, snapshot=checkpoint)
                return NavigationResult(False, False, target, NavigationState.FAILURE, snapshot=checkpoint, message="failure")

        controller = ResumeController()
        navigator = OpenPathNavigator(controller)
        with patch("navigation.path.observe_screen", return_value=different_screen):
            result = navigator.navigate("Open Settings and open Apps")

        self.assertFalse(result.success)
        self.assertFalse(result.resumed_from_checkpoint)
        self.assertEqual(controller.calls, [("Settings", "down"), ("Apps", "down")])


if __name__ == "__main__":
    unittest.main()
