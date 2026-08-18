import unittest
from unittest.mock import patch

from navigation.actions import activate_node, scroll
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

    def test_invalid_ancestor_bounds_are_rejected_before_transport(self):
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
        with patch("navigation.actions.subprocess.run") as transport:
            result = activate_node(node)
        self.assertFalse(result.success)
        self.assertFalse(transport.called)
        self.assertIn("valid live bounds", result.message)

    def test_non_clickable_node_uses_accessibility_semantic_activation(self):
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
        completed = type(
            "R",
            (),
            {"returncode": 0, "stdout": "Broadcast completed: result=1", "stderr": ""},
        )()
        with patch("navigation.actions.subprocess.run", return_value=completed) as transport:
            result = activate_node(node)

        self.assertTrue(result.success)
        command = transport.call_args.args[0]
        self.assertIn("com.infoney.nova.CLICK_ELEMENT", command)
        self.assertIn("Apps", command)
        self.assertEqual(result.bounds, "[50,50][250,250]")
        self.assertEqual(result.executor_returncode, 0)

    def test_accessibility_activation_failure_never_falls_back_to_root(self):
        rejected = type(
            "R",
            (),
            {"returncode": 0, "stdout": "Broadcast completed: result=0", "stderr": ""},
        )()
        node = {
            "text": "Apps",
            "clickable": True,
            "enabled": True,
            "bounds": "[100,100][200,200]",
        }
        with patch("navigation.actions.subprocess.run", return_value=rejected) as transport:
            result = activate_node(node)

        self.assertFalse(result.success)
        self.assertIn("Accessibility Service", result.message)
        self.assertEqual(transport.call_count, 1)

    def test_scroll_uses_accessibility_service_not_root_input(self):
        snapshot = self._snapshot(
            [],
            scrollable_regions=({"bounds": "[20,100][700,1500]"},),
        )
        completed = type(
            "R",
            (),
            {"returncode": 0, "stdout": "Broadcast completed: result=1", "stderr": ""},
        )()
        with patch("navigation.actions.subprocess.run", return_value=completed) as transport:
            result = scroll(snapshot, "down")

        self.assertTrue(result.success)
        command = transport.call_args.args[0]
        self.assertIn("com.infoney.nova.SCROLL_WINDOW", command)
        self.assertIn("down", command)
        self.assertNotIn("input", " ".join(command))

    def test_scroll_failure_is_bounded_and_reported(self):
        rejected = type(
            "R",
            (),
            {"returncode": 0, "stdout": "Broadcast completed: result=0", "stderr": ""},
        )()
        snapshot = self._snapshot(
            [],
            scrollable_regions=({"bounds": "[20,100][700,1500]"},),
        )
        with patch("navigation.actions.subprocess.run", return_value=rejected):
            result = scroll(snapshot, "down")

        self.assertFalse(result.success)
        self.assertIn("Accessibility Service", result.message)


if __name__ == "__main__":
    unittest.main()
