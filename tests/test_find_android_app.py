import unittest
from unittest.mock import patch

from tools.find_android_app import find_android_app


class FindAndroidAppTests(unittest.TestCase):
    def _packages(self, *names):
        return "\n".join(f"package:{name}" for name in names)

    def test_canonical_android_system_package_wins_over_other_settings_like_matches(self):
        output = self._packages(
            "com.example.settingsprovider",
            "com.android.settings",
            "com.transsion.settings",
        )
        completed = type("R", (), {"returncode": 0, "stdout": output, "stderr": ""})()
        with patch("tools.find_android_app.run_root", return_value=completed):
            result = find_android_app("Settings")

        self.assertTrue(result["success"])
        self.assertEqual(result["packages"], ["com.android.settings"])

    def test_ordinary_ambiguous_matches_remain_rejected(self):
        output = self._packages(
            "com.example.reader",
            "com.vendor.reader",
        )
        completed = type("R", (), {"returncode": 0, "stdout": output, "stderr": ""})()
        with patch("tools.find_android_app.run_root", return_value=completed):
            result = find_android_app("reader")

        self.assertFalse(result["success"])
        self.assertEqual(result["packages"], [])
        self.assertIn("ambiguous", result["message"].lower())


if __name__ == "__main__":
    unittest.main()
