import unittest
from unittest.mock import patch

from navigation.actions import ActionResult, activate_node, scroll
from navigation.resolver import resolve_target
from navigation.state import Resolution, ScreenSnapshot


class NavigationActionSafetyTests(unittest.TestCase):
    def _snapshot(self, nodes, scrollable_regions=()):
        return ScreenSnapshot(
            foreground_package="com.android.settings",
            visible_nodes=tuple(nodes),
            visible_text=tuple(
                str(node.get("text", ""))
                for node in nodes
                if str(node.get("text", "")).strip()
            ),
            scrollable_regions=tuple(scrollable_regions),
        )

    def test_exact_visible_label_wins_over_close_fuzzy_match(self):
        snapshot = self._snapshot(
            [
                {"text": "Apps", "clickable": False, "enabled": True},
                {"text": "App settings", "clickable": True, "enabled": True},
            ]
        )
        result = resolve_target(snapshot, "Apps")
        self.assertEqual(result.resolution, Resolution.FOUND)
        self.assertEqual(result.label, "Apps")

    def test_invalid_ancestor_bounds_are_rejected_before_activation(self):
        node = {
            "text": "Apps",
            "clickable": False,
            "enabled": True,
            "bounds": "[100,100][200,200]",
            "actionable_ancestor": {
                "clickable": True,
                "enabled": True,
                "bounds": "not-a-bounds",
            },
        }
        with patch("navigation.actions.subprocess.run") as accessibility_run:
            result = activate_node(node)
        self.assertFalse(result.success)
        self.assertFalse(accessibility_run.called)
        self.assertIn("valid live bounds", result.message)

    def test_accessibility_service_activation_does_not_call_root(self):
        node = {
            "text": "Apps",
            "clickable": False,
            "enabled": True,
            "bounds": "[100,100][200,200]",
            "actionable_ancestor": {
                "clickable": True,
                "enabled": True,
                "bounds": "[50,50][250,250]",
            },
        }
        accessibility_result = type(
            "R",
            (),
            {"returncode": 0, "stdout": "Broadcast completed: result=1", "stderr": ""},
        )()
        with patch("navigation.actions.subprocess.run", return_value=accessibility_result) as accessibility_run:
            result = activate_node(node)

        self.assertTrue(result.success)
        self.assertTrue(accessibility_run.called)
        self.assertEqual(result.bounds, "[50,50][250,250]")
        self.assertEqual(result.executor_returncode, 0)
        self.assertIsNotNone(result.duration_ms)
        self.assertEqual(result.transport_output, "Broadcast completed: result=1")
        command = accessibility_run.call_args.args[0]
        self.assertIn("com.infoney.nova.CLICK_ELEMENT", command)
        self.assertIn("Apps", command)

    def test_receiver_success_remains_success_when_am_exit_code_is_one(self):
        node = {
            "text": "Apps",
            "clickable": False,
            "enabled": True,
            "bounds": "[100,100][200,200]",
        }
        accessibility_result = type(
            "R",
            (),
            {"returncode": 1, "stdout": "Broadcast completed: result=1", "stderr": ""},
        )()
        with patch("navigation.actions.subprocess.run", return_value=accessibility_result) as accessibility_run:
            result = activate_node(node)

        self.assertTrue(result.success)
        self.assertEqual(result.executor_returncode, 1)
        self.assertEqual(result.transport_output, "Broadcast completed: result=1")
        self.assertTrue(accessibility_run.called)

    def test_accessibility_activation_failure_is_reported_without_root_fallback(self):
        node = {
            "text": "Apps",
            "clickable": False,
            "enabled": True,
            "bounds": "[100,100][200,200]",
        }
        accessibility_result = type(
            "R",
            (),
            {"returncode": 0, "stdout": "Broadcast completed: result=0", "stderr": ""},
        )()
        with patch("navigation.actions.subprocess.run", return_value=accessibility_result):
            result = activate_node(node)

        self.assertFalse(result.success)
        self.assertEqual(result.executor_returncode, 0)
        self.assertIsNotNone(result.duration_ms)
        self.assertEqual(result.transport_output, "Accessibility Service receiver rejected the requested action (result=0); no root fallback was attempted.")
        self.assertIn("Accessibility Service", result.message)

    def test_scroll_uses_accessibility_service_not_root_input(self):
        snapshot = self._snapshot(
            [],
            scrollable_regions=({"bounds": "[20,100][700,1500]"},),
        )
        accessibility_result = type(
            "R",
            (),
            {"returncode": 0, "stdout": "Broadcast completed: result=1", "stderr": ""},
        )()
        with patch("navigation.actions.subprocess.run", return_value=accessibility_result) as accessibility_run:
            result = scroll(snapshot, "down")

        self.assertTrue(result.success)
        self.assertEqual(result.executor_returncode, 0)
        self.assertIsNotNone(result.duration_ms)
        self.assertEqual(result.transport_output, "Broadcast completed: result=1")
        command = accessibility_run.call_args.args[0]
        self.assertIn("com.infoney.nova.SCROLL_WINDOW", command)
        self.assertIn("down", command)

    def test_scroll_accepts_receiver_success_with_am_exit_code_one(self):
        snapshot = self._snapshot(
            [],
            scrollable_regions=({"bounds": "[20,100][700,1500]"},),
        )
        accessibility_result = type(
            "R",
            (),
            {"returncode": 1, "stdout": "Broadcast completed: result=1", "stderr": ""},
        )()
        with patch("navigation.actions.subprocess.run", return_value=accessibility_result) as accessibility_run:
            result = scroll(snapshot, "down")

        self.assertTrue(result.success)
        self.assertEqual(result.executor_returncode, 1)
        self.assertEqual(result.transport_output, "Broadcast completed: result=1")
        self.assertTrue(accessibility_run.called)

    def test_scroll_rejects_invalid_region_without_accessibility_call(self):
        snapshot = self._snapshot(
            [],
            scrollable_regions=({"bounds": "invalid"},),
        )
        with patch("navigation.actions.subprocess.run") as accessibility_run:
            result = scroll(snapshot, "down")
        self.assertFalse(result.success)
        self.assertFalse(accessibility_run.called)
        self.assertIn("invalid live bounds", result.message)


if __name__ == "__main__":
    unittest.main()
