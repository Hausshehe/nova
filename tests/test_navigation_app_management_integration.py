import unittest
from types import SimpleNamespace
from unittest.mock import patch

from navigation.actions import ActionResult
from navigation.controller import NavigationController, NavigationState
from navigation.state import ScreenSnapshot
from navigation.verifier import VerificationResult


class NavigationAppManagementIntegrationTests(unittest.TestCase):
    def _snapshot(self, labels):
        nodes = tuple(
            {
                "text": label,
                "content_description": "",
                "resource_id": "",
                "class": "android.widget.TextView",
                "package": "com.android.settings",
                "bounds": f"[24,{700 + index * 100}][696,{780 + index * 100}]",
                "clickable": False,
                "enabled": True,
                "focusable": False,
                "scrollable": False,
                "actionable_ancestor": {
                    "bounds": f"[0,{680 + index * 100}][720,{800 + index * 100}]",
                    "clickable": True,
                    "enabled": True,
                },
            }
            for index, label in enumerate(labels)
        )
        return ScreenSnapshot(
            foreground_package="com.android.settings",
            visible_nodes=nodes,
            visible_text=tuple(labels),
            scrollable_regions=({"bounds": "[0,420][720,1532]"},),
        )

    def test_full_navigation_resolves_apps_to_app_management_after_scroll(self):
        before = self._snapshot(("Settings", "Display & Brightness", "Sound & Vibration"))
        after_scroll = self._snapshot(("Privacy", "Storage", "App Management", "Location"))
        refreshed = self._snapshot(("Privacy", "Storage", "App Management", "Location"))
        result_screen = self._snapshot(("App Management", "Default apps", "Permissions"))

        scroll_result = ActionResult(True, "SCROLL", "semantic accessibility scroll", "[0,420][720,1532]")
        click_result = ActionResult(True, "TAP", "semantic accessibility activation", "[0,880][720,1040]")
        verification = VerificationResult(True, result_screen, "verified destination transition")

        controller = NavigationController(
            observation_retries=1,
            settle_seconds=0,
            max_scrolls=2,
            max_activation_retries=0,
        )

        with patch(
            "navigation.controller.observe_screen",
            side_effect=[before, after_scroll, refreshed],
        ), patch("navigation.controller.scroll", return_value=scroll_result), patch(
            "navigation.controller.activate_node", return_value=click_result
        ) as activate, patch(
            "navigation.controller.verify_transition", return_value=verification
        ):
            result = controller.navigate_target("Apps", expected_foreground_package="com.android.settings")

        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertEqual(result.state, NavigationState.SUCCESS)
        self.assertEqual(result.scroll_count, 1)
        self.assertEqual(result.match.label, "App Management")
        self.assertEqual(activate.call_count, 1)
        self.assertIn(NavigationState.SCROLL, result.history)
        self.assertIn(NavigationState.REOBSERVE, result.history)
        self.assertIn(NavigationState.ACTIVATE, result.history)
        self.assertIn(NavigationState.VERIFY, result.history)
        self.assertIn(NavigationState.SUCCESS, result.history)


if __name__ == "__main__":
    unittest.main()
