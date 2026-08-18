import unittest

from navigation.resolver import resolve_target
from navigation.state import Resolution, ScreenSnapshot


class NavigationResolverSemanticLabelTests(unittest.TestCase):
    def test_apps_goal_matches_app_management_live_label(self):
        snapshot = ScreenSnapshot(
            foreground_package="com.android.settings",
            visible_nodes=(
                {
                    "text": "App Management",
                    "content_description": "",
                    "resource_id": "",
                    "class": "android.widget.TextView",
                    "package": "com.android.settings",
                    "bounds": "[24,900][696,1020]",
                    "clickable": False,
                    "enabled": True,
                    "focusable": False,
                    "scrollable": False,
                    "actionable_ancestor": {
                        "bounds": "[0,880][720,1040]",
                        "clickable": True,
                        "enabled": True,
                    },
                },
            ),
            visible_text=("App Management",),
            scrollable_regions=({"bounds": "[0,316][720,1512]"},),
        )

        result = resolve_target(snapshot, "Apps")

        self.assertEqual(result.resolution, Resolution.FOUND)
        self.assertEqual(result.label, "App Management")
        self.assertIsNotNone(result.node)
        self.assertGreaterEqual(result.score, 50.0)


if __name__ == "__main__":
    unittest.main()
