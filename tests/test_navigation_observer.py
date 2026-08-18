import unittest
from unittest.mock import patch
from types import SimpleNamespace

from navigation.observer import observe_screen
from navigation.state import ObservationQuality, ScreenSnapshot


class NavigationObserverTests(unittest.TestCase):
    def test_fresh_accessibility_snapshot_is_preferred_over_uiautomator(self):
        accessibility = {
            "source": "accessibility_service",
            "timestamp_ms": 9999999999999,
            "foreground_package": "com.android.settings",
            "nodes": [
                {
                    "text": "Apps",
                    "content_description": "",
                    "resource_id": "",
                    "class": "android.widget.TextView",
                    "package": "com.android.settings",
                    "bounds": "[0,100][720,180]",
                    "clickable": False,
                    "enabled": True,
                    "actionable_ancestor": {
                        "bounds": "[0,80][720,200]",
                        "clickable": True,
                        "enabled": True,
                    },
                }
            ],
            "scrollable": ["[0,212][720,1452]"],
        }
        with patch("navigation.observer.read_accessibility_snapshot", return_value=accessibility), patch(
            "navigation.observer.observe_android"
        ) as uiautomator:
            result = observe_screen(retries=1, settle_seconds=0)

        uiautomator.assert_not_called()
        self.assertEqual(result.observation_quality, ObservationQuality.VALID)
        self.assertEqual(result.foreground_package, "com.android.settings")
        self.assertEqual(result.visible_text, ("Apps",))
        self.assertTrue(result.scrollable)

    def test_stale_accessibility_snapshot_falls_back_to_uiautomator(self):
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
        with patch("navigation.observer.read_accessibility_snapshot", return_value=None), patch(
            "navigation.observer.observe_android", return_value=observed
        ) as uiautomator:
            result = observe_screen(retries=1, settle_seconds=0)

        uiautomator.assert_called_once_with(include_nodes=True)
        self.assertEqual(result.observation_quality, ObservationQuality.VALID)
        self.assertEqual(result.visible_text, ("Apps",))

    def test_foreground_only_observation_is_transient(self):
        empty = {
            "success": True,
            "foreground_package": "com.android.settings",
            "state": {},
            "nodes": [],
        }
        with patch("navigation.observer.read_accessibility_snapshot", return_value=None), patch(
            "navigation.observer.observe_android", return_value=empty
        ):
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
        with patch("navigation.observer.read_accessibility_snapshot", return_value=None), patch(
            "navigation.observer.observe_android", return_value=failed
        ):
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
        with patch("navigation.observer.read_accessibility_snapshot", return_value=None), patch(
            "navigation.observer.observe_android", return_value=observed
        ):
            result = observe_screen(retries=1, settle_seconds=0)

        self.assertEqual(result.observation_quality, ObservationQuality.VALID)
        self.assertEqual(result.visible_text, ("Apps",))


class LowLevelObservationTests(unittest.TestCase):
    def test_low_level_observation_uses_one_bounded_dump_attempt(self):
        import tools.observe_android as observer

        timed_out = SimpleNamespace(returncode=124, stdout="", stderr="Command timed out")
        with patch.object(observer, "run_root", return_value=timed_out) as run_root:
            result = observer.observe_android(include_nodes=True)

        self.assertFalse(result["success"])
        self.assertEqual(run_root.call_count, 2)
        self.assertEqual(run_root.call_args_list[0].args[0].startswith("rm -f"), True)
        self.assertIn("dumpsys activity", run_root.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
