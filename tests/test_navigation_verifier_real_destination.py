import unittest
from unittest.mock import patch

from navigation.state import ScreenSnapshot
from navigation.verifier import verify_transition


class NavigationVerifierRealDestinationTests(unittest.TestCase):
    def _snapshot(self, text):
        nodes = tuple(
            {
                "text": value,
                "content_description": "",
                "resource_id": "",
                "class": "android.widget.TextView",
                "package": "com.android.settings",
                "bounds": f"[40,{800 + index * 90}][680,{860 + index * 90}]",
                "clickable": False,
                "enabled": True,
                "actionable_ancestor": {
                    "bounds": f"[40,{780 + index * 90}][680,{880 + index * 90}]",
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
            scrollable_regions=({"bounds": "[0,316][720,1512]"},),
        )

    def test_verifier_accepts_destination_apps_while_source_app_management_remains_visible(self):
        before = self._snapshot(("App Management", "Location", "Battery Lab"))
        after = self._snapshot((
            "Navigate up",
            "App Management",
            "Apps",
            "App list",
            "Assistant",
            "Default apps",
            "Permissions",
        ))

        with patch("navigation.verifier.observe_screen", side_effect=[after, after]):
            result = verify_transition(
                before,
                expected_foreground_package="com.android.settings",
                expected_target="Apps",
                timeout_seconds=0.2,
                poll_seconds=0,
            )

        self.assertTrue(result.success)
        self.assertTrue(result.target_resolved)
        self.assertIn("destination-aware", result.reason)


if __name__ == "__main__":
    unittest.main()
