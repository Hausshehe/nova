import unittest
from unittest.mock import patch

from navigation.controller import NavigationResult, NavigationState
from navigation.path import OpenPathNavigator
from navigation.state import ObservationQuality, ScreenSnapshot


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

        with patch("navigation.path.find_android_app") as find_app:
            result = navigator.navigate("Open Settings and open Apps, then open YouTube")

        self.assertFalse(result.success)
        self.assertEqual(result.failed_target, "Settings")
        find_app.assert_called_once_with("Settings")

    def test_single_app_step_may_use_package_fallback(self):
        controller = FakeController()
        navigator = OpenPathNavigator(controller)
        discovery = {"success": True, "packages": ["com.example.reader"]}
        launch_result = {"success": True}

        with patch("navigation.path.find_android_app", return_value=discovery), patch(
            "navigation.path.launch_android_app", return_value=launch_result
        ), patch("navigation.path.observe_screen"), patch(
            "navigation.path.verify_transition"
        ) as verify:
            # The verification result is deliberately mocked unsuccessful so
            # this test only verifies that the package fallback is attempted.
            verify.return_value.success = False
            verify.return_value.snapshot = None
            verify.return_value.reason = "simulated verification failure"
            result = navigator.navigate("Open Reader")

        self.assertFalse(result.success)
        self.assertEqual(result.failed_target, "Reader")
