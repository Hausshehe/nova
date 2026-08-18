import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.navigate_android_to import navigate_android_to


class NavigationAdapterTests(unittest.TestCase):
    def test_adapter_preserves_result_contract_and_direction(self):
        class FakeController:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.calls = []

            def navigate_target(self, target, *, initial_direction):
                self.calls.append((target, initial_direction))
                return SimpleNamespace(
                    success=True,
                    verified=True,
                    scroll_count=2,
                    match=SimpleNamespace(label=target, score=100.0),
                    snapshot=SimpleNamespace(foreground_package="com.android.settings"),
                    state=SimpleNamespace(value="SUCCESS"),
                    history=(SimpleNamespace(value="OBSERVE"), SimpleNamespace(value="SUCCESS")),
                )

        with patch("tools.navigate_android_to.NavigationController", FakeController):
            result = navigate_android_to("Apps", max_scrolls=5, direction="up")

        self.assertTrue(result["success"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["scrolls"], 2)
        self.assertEqual(result["foreground_package"], "com.android.settings")


if __name__ == "__main__":
    unittest.main()
