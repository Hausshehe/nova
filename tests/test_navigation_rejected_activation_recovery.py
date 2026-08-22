import unittest
from types import SimpleNamespace
from unittest.mock import patch

from navigation.actions import ActionResult
from navigation.controller import NavigationController, NavigationState
from navigation.state import ScreenSnapshot
from navigation.verifier import VerificationResult


class NavigationRejectedActivationRecoveryTests(unittest.TestCase):
    def _snapshot(self, text=("App Management",), package="com.android.settings"):
        nodes = tuple(
            {
                "text": value,
                "content_description": "",
                "resource_id": "",
                "class": "android.widget.TextView",
                "package": package,
                "bounds": f"[40,{100 + index * 100}][680,{180 + index * 100}]",
                "clickable": False,
                "enabled": True,
                "focusable": False,
                "scrollable": False,
                "actionable_ancestor": {
                    "bounds": f"[20,{80 + index * 100}][700,{200 + index * 100}]",
                    "clickable": True,
                    "enabled": True,
                },
            }
            for index, value in enumerate(text)
        )
        return ScreenSnapshot(
            foreground_package=package,
            visible_nodes=nodes,
            visible_text=tuple(text),
        )

    def test_rejected_activation_reobserves_reresolves_and_retries_once(self):
        initial = self._snapshot()
        refreshed = self._snapshot()
        destination = self._snapshot(("Navigate up", "App Management", "Apps", "App list"))
        rejected = ActionResult(False, "TAP", "Accessibility Service receiver rejected the requested action (result=0).")
        accepted = ActionResult(True, "TAP", "Accessibility activation accepted; higher-level verification is required.")
        verified = VerificationResult(True, destination, "verified", target_resolved=True)
        controller = NavigationController(observation_retries=1, max_activation_retries=1, settle_seconds=0, max_scrolls=0)

        with patch("navigation.controller.observe_screen", side_effect=[initial, refreshed, destination]), \
             patch("navigation.controller.resolve_target", wraps=__import__("navigation.resolver", fromlist=["resolve_target"]).resolve_target) as resolve, \
             patch("navigation.controller.activate_node", side_effect=[rejected, accepted]) as activate, \
             patch("navigation.controller.verify_transition", return_value=verified):
            result = controller.navigate_target("App Management")

        self.assertTrue(result.success)
        self.assertEqual(result.state, NavigationState.SUCCESS)
        self.assertEqual(activate.call_count, 2)
        self.assertGreaterEqual(resolve.call_count, 2)
        self.assertIn(NavigationState.RECOVER, result.history)

    def test_rejected_activation_stops_after_single_bounded_retry(self):
        initial = self._snapshot()
        refreshed = self._snapshot()
        rejected = ActionResult(False, "TAP", "Accessibility Service receiver rejected the requested action (result=0).")
        controller = NavigationController(observation_retries=1, max_activation_retries=1, settle_seconds=0, max_scrolls=0)

        with patch("navigation.controller.observe_screen", side_effect=[initial, refreshed]), \
             patch("navigation.controller.activate_node", side_effect=[rejected, rejected]) as activate:
            result = controller.navigate_target("App Management")

        self.assertFalse(result.success)
        self.assertEqual(result.state, NavigationState.FAILURE)
        self.assertEqual(activate.call_count, 2)
        self.assertEqual(result.history.count(NavigationState.ACTIVATE), 2)
        self.assertEqual(result.history.count(NavigationState.RECOVER), 2)


if __name__ == "__main__":
    unittest.main()
