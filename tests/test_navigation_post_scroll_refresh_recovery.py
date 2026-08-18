import unittest
from unittest.mock import patch

from navigation.actions import ActionResult
from navigation.controller import NavigationController
from navigation.state import ScreenSnapshot
from navigation.verifier import VerificationResult


class NavigationPostScrollRefreshRecoveryTests(unittest.TestCase):
    def _snapshot(self, text, *, scrollable=True):
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
            scrollable_regions=({"bounds": "[0,212][720,1452]"},) if scrollable else (),
        )

    def test_post_scroll_match_survives_stale_refresh(self):
        initial = self._snapshot(("Settings", "Wi-Fi", "Display"))
        after_scroll = self._snapshot(("Display", "Privacy", "Storage"))
        stale_refresh = self._snapshot(("Settings", "Wi-Fi", "Display"))
        tap = ActionResult(True, "TAP", "simulated")
        verified = VerificationResult(True, after_scroll, "simulated verified transition")
        controller = NavigationController(observation_retries=1, max_scrolls=1, settle_seconds=0)

        with patch(
            "navigation.controller.observe_screen",
            side_effect=[initial, after_scroll, stale_refresh],
        ), patch("navigation.controller.scroll", return_value=ActionResult(True, "SCROLL", "simulated")), patch(
            "navigation.controller.activate_node", return_value=tap
        ) as activate, patch("navigation.controller.verify_transition", return_value=verified):
            result = controller.navigate_target("Privacy")

        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertEqual(result.scroll_count, 1)
        self.assertEqual(activate.call_count, 1)
        self.assertEqual(result.match.label, "Privacy")


if __name__ == "__main__":
    unittest.main()
