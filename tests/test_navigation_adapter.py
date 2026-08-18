import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.navigate_android_to import navigate_android_to


class NavigationAdapterTests(unittest.TestCase):
    def test_adapter_preserves_result_contract_and_direction(self):
        calls = []

        class FakeController:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def navigate_target(self, target, *, initial_direction):
                calls.append((target, initial_direction))
                return SimpleNamespace(
                    success=True,
                    verified=True,
                    scroll_count=2,
                    match=SimpleNamespace(label=target, score=100.0),
                    snapshot=SimpleNamespace(foreground_package="com.android.settings"),
                    state=SimpleNamespace(value="SUCCESS"),
                    history=(SimpleNamespace(value="OBSERVE"), SimpleNamespace(value="SUCCESS")),
                )

        class FakeNavigator:
            def __init__(self, controller, *, initial_direction):
                self.controller = controller
                self.initial_direction = initial_direction
                self.checkpoints = SimpleNamespace(
                    latest=SimpleNamespace(
                        snapshot=SimpleNamespace(foreground_package="com.android.settings")
                    )
                )

            def navigate(self, goal):
                self.controller.navigate_target("Apps", initial_direction=self.initial_direction)
                return SimpleNamespace(
                    success=True,
                    verified=True,
                    completed_targets=["Apps"],
                    failed_target="",
                    checkpoints=1,
                    resumed_from_checkpoint=False,
                    message="verified",
                )

        with patch("tools.navigate_android_to.NavigationController", FakeController), patch(
            "tools.navigate_android_to.OpenPathNavigator", FakeNavigator
        ):
            result = navigate_android_to("Apps", max_scrolls=5, direction="up")

        self.assertTrue(result["success"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["checkpoints"], 1)
        self.assertEqual(result["foreground_package"], "com.android.settings")
        self.assertEqual(calls, [("Apps", "up")])


if __name__ == "__main__":
    unittest.main()
