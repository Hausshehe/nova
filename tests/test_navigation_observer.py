import unittest
from unittest.mock import patch

from navigation.observer import observe_screen
from navigation.state import ObservationQuality, ScreenSnapshot


class NavigationObserverTests(unittest.TestCase):
    def test_foreground_only_observation_is_transient(self):
        empty = {
            "success": True,
            "foreground_package": "com.android.settings",
            "state": {},
            "nodes": [],
        }
        with patch("navigation.observer.observe_android", return_value=empty):
            result = observe_screen(retries=1, settle_seconds=0)

        self.assertEqual(result.observation_quality, ObservationQuality.TRANSIENT)
        self.assertEqual(result.foreground_package, "com.android.settings")
        self.assertIn("no usable navigation UI", result.message)

    def test_failed_observation_preserves_last_valid_snapshot_as_transient(self):
        previous = ScreenSnapshot(
            foreground_package="com.android.settings",
            visible_text=("Apps", "Display"),
            observation_quality=ObservationQuality.VALID,
        )
        failed = {
            "success": False,
            "foreground_package": "",
            "message": "uiautomator timeout",
        }
        with patch("navigation.observer.observe_android", return_value=failed):
            result = observe_screen(previous=previous, retries=1, settle_seconds=0)

        self.assertEqual(result.observation_quality, ObservationQuality.TRANSIENT)
        self.assertEqual(result.foreground_package, previous.foreground_package)
        self.assertEqual(result.visible_text, previous.visible_text)
        self.assertIn("retaining the last valid snapshot", result.message)

    def test_valid_hierarchy_is_returned_as_valid(self):
        observed = {
            "success": True,
            "foreground_package": "com.android.settings",
            "state": {
                "visible_text": ["Apps"],
                "interactive": [],
                "scrollable": [],
            },
            "nodes": [
                {"text": "Apps", "bounds": "[0,100][720,180]", "enabled": True}
            ],
        }
        with patch("navigation.observer.observe_android", return_value=observed):
            result = observe_screen(retries=1, settle_seconds=0)

        self.assertEqual(result.observation_quality, ObservationQuality.VALID)
        self.assertEqual(result.visible_text, ("Apps",))


if __name__ == "__main__":
    unittest.main()
