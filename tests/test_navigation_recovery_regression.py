import unittest
from types import SimpleNamespace
from unittest.mock import patch

from navigation.actions import ActionResult
from navigation.controller import NavigationController, NavigationState
from navigation.state import ScreenSnapshot
from navigation.verifier import VerificationResult


class NavigationRecoveryRegressionTests(unittest.TestCase):
    def _snapshot(self, text):
        nodes = tuple(
            {
                "text": value,
                "content_description": "",
                "resource_id": "",
                "class": "android.widget.TextView",
                "package": "com.android.settings",
                "bounds": f"[0,{index * 100}][720,{index * 100 + 80}]",
                "clickable": False,
                "enabled": True,
                "focusable": False,
                "actionable_ancestor": {
                    "bounds": f"[0,{index * 100}][720,{index * 100 + 80}]",
                    "clickable": True,
                    "enabled": True,
                },
            }
            for index, value in enumerate(text)
        )
        return ScreenSnapshot(
            foreground_package="com.android.settings",
            visible_nodes=nodes,
            visible_text=tuple(text),
            scrollable_regions=({"bounds": "[0,212][720,1452]"},),
        )

    def _controller(self):
        return NavigationController(
            observation_retries=1,
            max_activation_retries=1,
            settle_seconds=0,
            max_scrolls=0,
        )

    def test_recovery_does_not_accept_same_screen_change_while_target_remains(self):
        initial = self._snapshot(("Apps", "Display", "Battery"))
        still_same_target = self._snapshot(("Apps", "Display", "Storage"))
        action = ActionResult(True, "TAP", "simulated")
        failed = VerificationResult(False, still_same_target, "simulated delayed transition")

        with patch("navigation.controller.observe_screen", side_effect=[initial, still_same_target]), patch(
            "navigation.controller.activate_node", return_value=action
        ), patch("navigation.controller.verify_transition", return_value=failed):
            result = self._controller().navigate_target("Apps")

        self.assertFalse(result.success)
        self.assertEqual(result.state, NavigationState.FAILURE)
        self.assertIn("re-resolved", result.message)

    def test_recovery_accepts_meaningful_destination_after_target_disappears(self):
        initial = self._snapshot(("Apps", "Display", "Battery"))
        destination = self._snapshot(("App list", "Assistant", "Screen time"))
        action = ActionResult(True, "TAP", "simulated")
        failed = VerificationResult(False, initial, "simulated delayed transition")

        with patch("navigation.controller.observe_screen", side_effect=[initial, destination]), patch(
            "navigation.controller.activate_node", return_value=action
        ), patch("navigation.controller.verify_transition", return_value=failed):
            result = self._controller().navigate_target("Apps")

        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertEqual(result.state, NavigationState.SUCCESS)

    def test_geometry_mismatch_gets_fresh_resolution_before_tap_retry(self):
        initial = self._snapshot(("Apps", "Display"))
        refreshed = self._snapshot(("Apps", "Display"))
        geometry_failure = ActionResult(False, "TAP", "Actionable ancestor bounds do not contain the target bounds.")
        tap_success = ActionResult(True, "TAP", "fresh live target activated")
        verified = VerificationResult(True, refreshed, "simulated verified transition")

        with patch("navigation.controller.observe_screen", side_effect=[initial, refreshed]), patch(
            "navigation.controller.activate_node", side_effect=[geometry_failure, tap_success]
        ) as activate, patch("navigation.controller.verify_transition", return_value=verified):
            result = self._controller().navigate_target("Apps")

        self.assertTrue(result.success)
        self.assertEqual(activate.call_count, 2)
        self.assertEqual(result.state, NavigationState.SUCCESS)
        self.assertIn(NavigationState.RECOVER, result.history)


if __name__ == "__main__":
    unittest.main()
