import unittest
from unittest.mock import patch

from navigation.controller import NavigationController, NavigationState
from navigation.progress import compare_snapshots
from navigation.resolver import resolve_target
from navigation.state import ObservationQuality, Resolution, ScreenSnapshot
from navigation.verifier import verify_transition


class NavigationCoreTests(unittest.TestCase):
    def _snapshot(self, *, text, package="com.android.settings", scrollable=True):
        nodes = tuple(
            {
                "text": value,
                "content_description": "",
                "resource_id": "",
                "class": "android.widget.TextView",
                "package": package,
                "bounds": f"[0,{index * 100}][720,{index * 100 + 80}]",
                "clickable": False,
                "enabled": True,
                "focusable": False,
                "actionable_ancestor": {
                    "bounds": f"[0,{index * 100}][720,{index * 100 + 80}]",
                    "clickable": True,
                    "enabled": True,
                },
            }
            for index, value in enumerate(text)
        )
        return ScreenSnapshot(
            foreground_package=package,
            visible_nodes=nodes,
            visible_text=tuple(text),
            scrollable_regions=({"bounds": "[0,212][720,1452]"},) if scrollable else (),
        )

    def test_apps_prefers_visible_settings_destination(self):
        snapshot = self._snapshot(text=("Battery", "Apps", "Display"))
        result = resolve_target(snapshot, "Apps", installed_packages=("com.example.apps", "com.google.android.youtube"))
        self.assertEqual(result.resolution, Resolution.FOUND)
        self.assertEqual(result.label, "Apps")

    def test_transient_observation_is_not_resolvable(self):
        snapshot = self._snapshot(text=("Apps",))
        transient = ScreenSnapshot(
            foreground_package=snapshot.foreground_package,
            visible_nodes=snapshot.visible_nodes,
            visible_text=snapshot.visible_text,
            scrollable_regions=snapshot.scrollable_regions,
            observation_quality=ObservationQuality.TRANSIENT,
        )
        result = resolve_target(transient, "Apps")
        self.assertEqual(result.resolution, Resolution.INVALID_OBSERVATION)

    def test_snapshot_change_counts_as_progress(self):
        before = self._snapshot(text=("A", "B", "C"))
        after = self._snapshot(text=("D", "E", "F"))
        result = compare_snapshots(before, after)
        self.assertTrue(result.meaningful)
        self.assertTrue(result.new_text)

    def test_identical_snapshot_is_not_progress(self):
        snapshot = self._snapshot(text=("A", "B", "C"))
        result = compare_snapshots(snapshot, snapshot)
        self.assertFalse(result.meaningful)

    def test_repeated_transient_observations_are_bounded(self):
        transient = ScreenSnapshot(
            foreground_package="com.android.settings",
            observation_quality=ObservationQuality.TRANSIENT,
            message="simulated transient hierarchy",
        )
        controller = NavigationController(
            observation_retries=1,
            max_transient_observations=3,
            max_scrolls=1,
        )
        with patch("navigation.controller.observe_screen", return_value=transient) as observe:
            result = controller.navigate_target("Apps")

        self.assertFalse(result.success)
        self.assertEqual(result.state, NavigationState.FAILURE)
        self.assertEqual(observe.call_count, 3)
        self.assertIn("bounded recovery budget", result.message)

    def test_ambiguous_visible_targets_are_rejected(self):
        snapshot = self._snapshot(text=("App settings", "App options"))
        result = resolve_target(snapshot, "App")
        self.assertEqual(result.resolution, Resolution.AMBIGUOUS)
        self.assertIsNone(result.node)
        self.assertIn("Multiple visible controls", result.reason)

    def test_verifier_rejects_incidental_bounds_only_change(self):
        before = self._snapshot(text=("Apps", "Display"))
        after = self._snapshot(text=("Apps", "Display"))
        with patch("navigation.verifier.observe_screen", return_value=after):
            result = verify_transition(
                before,
                timeout_seconds=0.2,
                poll_seconds=0,
            )
        self.assertFalse(result.success)
        self.assertIn("meaningful semantic UI transition", result.reason)

    def test_verifier_accepts_meaningful_text_transition(self):
        before = self._snapshot(text=("Apps", "Display", "Battery"))
        after = self._snapshot(text=("App list", "Assistant", "Screen time"))
        with patch("navigation.verifier.observe_screen", return_value=after):
            result = verify_transition(
                before,
                timeout_seconds=0.2,
                poll_seconds=0,
            )
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
