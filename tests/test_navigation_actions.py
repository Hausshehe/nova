import unittest
from unittest.mock import patch

from navigation.actions import ActionResult, activate_node
from navigation.resolver import resolve_target
from navigation.state import Resolution, ScreenSnapshot


class NavigationActionSafetyTests(unittest.TestCase):
    def _snapshot(self, nodes):
        return ScreenSnapshot(
            foreground_package="com.android.settings",
            visible_nodes=tuple(nodes),
            visible_text=tuple(
                str(node.get("text", ""))
                for node in nodes
                if str(node.get("text", "")).strip()
            ),
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

    def test_invalid_ancestor_bounds_are_not_used_for_activation(self):
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
        with patch("navigation.actions.run_root") as run_root, patch(
            "navigation.actions.subprocess.run"
        ) as accessibility_run:
            result = activate_node(node)
        self.assertFalse(result.success)
        self.assertFalse(run_root.called)
        self.assertFalse(accessibility_run.called)
        self.assertIn("valid live bounds", result.message)

    def test_accessibility_service_activation_precedes_root_fallback(self):
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
        with patch("navigation.actions.subprocess.run", return_value=accessibility_result) as accessibility_run, patch(
            "navigation.actions.run_root"
        ) as run_root:
            result = activate_node(node)

        self.assertTrue(result.success)
        self.assertTrue(accessibility_run.called)
        self.assertFalse(run_root.called)
        self.assertEqual(result.bounds, "[50,50][250,250]")
        command = accessibility_run.call_args.args[0]
        self.assertIn("com.infoney.nova.CLICK_ELEMENT", command)
        self.assertIn("Apps", command)

    def test_root_activation_is_bounded_fallback_when_accessibility_activation_fails(self):
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
            {"returncode": 0, "stdout": "Broadcast completed: result=0", "stderr": ""},
        )()
        root_result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch("navigation.actions.subprocess.run", return_value=accessibility_result), patch(
            "navigation.actions.run_root", return_value=root_result
        ) as run_root:
            result = activate_node(node)

        self.assertTrue(result.success)
        self.assertTrue(run_root.called)
        self.assertIn("root fallback", result.message)

    def test_non_clickable_node_can_use_valid_actionable_ancestor(self):
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
        with patch("navigation.actions.subprocess.run", return_value=accessibility_result) as accessibility_run, patch(
            "navigation.actions.run_root"
        ) as run_root:
            result = activate_node(node)

        self.assertTrue(result.success)
        self.assertTrue(accessibility_run.called)
        self.assertFalse(run_root.called)
        self.assertEqual(result.bounds, "[50,50][250,250]")


if __name__ == "__main__":
    unittest.main()
