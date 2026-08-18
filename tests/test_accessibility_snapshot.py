import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.accessibility_snapshot import read_accessibility_snapshot


class AccessibilitySnapshotTests(unittest.TestCase):
    def _result(self, payload, returncode=0):
        return SimpleNamespace(returncode=returncode, stdout=json.dumps(payload), stderr="")

    def test_fresh_service_snapshot_is_returned(self):
        payload = {
            "source": "accessibility_service",
            "timestamp_ms": int(time.time() * 1000),
            "foreground_package": "com.android.settings",
            "nodes": [{"text": "Apps"}],
            "scrollable": ["[0,212][720,1452]"],
        }
        with patch("tools.accessibility_snapshot.run_root", return_value=self._result(payload)):
            result = read_accessibility_snapshot(max_age_seconds=2)

        self.assertIsNotNone(result)
        self.assertEqual(result["foreground_package"], "com.android.settings")

    def test_stale_service_snapshot_is_rejected(self):
        payload = {
            "source": "accessibility_service",
            "timestamp_ms": int(time.time() * 1000) - 10000,
            "foreground_package": "com.android.settings",
            "nodes": [{"text": "Apps"}],
        }
        with patch("tools.accessibility_snapshot.run_root", return_value=self._result(payload)):
            result = read_accessibility_snapshot(max_age_seconds=2)

        self.assertIsNone(result)

    def test_non_accessibility_source_is_rejected(self):
        payload = {
            "source": "uiautomator",
            "timestamp_ms": int(time.time() * 1000),
            "foreground_package": "com.android.settings",
            "nodes": [{"text": "Apps"}],
        }
        with patch("tools.accessibility_snapshot.run_root", return_value=self._result(payload)):
            result = read_accessibility_snapshot(max_age_seconds=2)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
