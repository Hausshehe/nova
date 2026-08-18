import unittest
from unittest.mock import patch

from navigation.actions import ActionResult
from navigation.controller import NavigationController, NavigationState
from navigation.state import ScreenSnapshot
from navigation.verifier import VerificationResult


class PostScrollActivationTests(unittest.TestCase):
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
                "scrollable": False,
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

    def test_target_visible_after_scroll_is_activated_without_extra_scroll(self):
        initial = self._snapshot(("Battery", "Display"))
        after_scroll = self._snapshot(("Battery", "Apps"))
        refreshed_after_scroll = self._snapshot(("Battery", "Apps"))
        destination = self._snapshot(("App list", "Assistant"))
        scroll_result = ActionResult(True, "SCROLL", "simulated")
        tap_result = ActionResult(True, "TAP", "simulated")
        verification = VerificationResult(True, destination, "simulated verified transition")

        controller = NavigationController(
            observation_retries=1,
            max_scrolls=3,
            settle_seconds=0,
        )

        with patch(
            "navigation.controller.observe_screen",
            side_effect=[initial, after_scroll, refreshed_after_scroll],
        ), patch("navigation.controller.scroll", return_value=scroll_result) as scroll, patch(
            "navigation.controller.activate_node", return_value=tap_result
        ) as activate, patch(
            "navigation.controller.verify_transition", return_value=verification
        ):
            result = controller.navigate_target("Apps")

        self.assertTrue(result.success)
        self.assertEqual(scroll.call_count, 1)
        self.assertEqual(activate.call_count, 1)
        self.assertIn(NavigationState.SCROLL, result.history)
        self.assertIn(NavigationState.ACTIVATE, result.history)
        self.assertIn(NavigationState.SUCCESS, result.history)


if __name__ == "__main__":
    unittest.main()
