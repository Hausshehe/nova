import unittest
from unittest.mock import patch

from navigation.controller import NavigationResult, NavigationState
from navigation.path import OpenPathNavigator
from navigation.state import ObservationQuality, ScreenSnapshot
from navigation.verifier import VerificationResult


class FakeController:
    def __init__(self):
        self.calls = []

    def navigate_target(self, target):
        self.calls.append(target)
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


if __name__ == "__main__":
    unittest.main()
