import unittest
from unittest.mock import patch

from navigation.actions import ActionResult
from navigation.controller import NavigationController, NavigationState
from navigation.state import Resolution, ScreenSnapshot
from navigation.verifier import VerificationResult


class FreshSearchRegressionTests(unittest.TestCase):
    def _snapshot(self, text, scrollable=True):
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
            scrollable_regions=({"bounds": "[0,212][720,1452]"},) if scrollable else (),
        )

    def test_visible_target_found_on_fresh_corroboration_before_scroll(self):
        stale = self._snapshot(("Settings", "Search settings"))
        fresh = self._snapshot(("Settings", "Search settings", "Bluetooth"))
        destination = self._snapshot(("Navigate up", "Bluetooth", "Device Name"), scrollable=False)
        tap = ActionResult(True, "TAP", "accepted")
        verified = VerificationResult(True, destination, "verified", target_resolved=True)

        controller = NavigationController(observation_retries=1, max_scrolls=3, max_activation_retries=0, settle_seconds=0)
        with patch("navigation.controller.observe_screen", side_effect=[stale, fresh]), \
             patch("navigation.controller.scroll") as do_scroll, \
             patch("navigation.controller.activate_node", return_value=tap) as activate, \
             patch("navigation.controller.verify_transition", return_value=verified):
            result = controller.navigate_target("Bluetooth")

        self.assertTrue(result.success)
        self.assertEqual(activate.call_count, 1)
        self.assertFalse(do_scroll.called)
        self.assertIn(NavigationState.REOBSERVE, result.history)
        self.assertEqual(result.state, NavigationState.SUCCESS)


if __name__ == "__main__":
    unittest.main()
