import unittest

from navigation.progress import compare_snapshots
from navigation.resolver import resolve_target
from navigation.state import ObservationQuality, Resolution, ScreenSnapshot


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
            scrollable_regions=(
                {"bounds": "[0,212][720,1452]"},
            )
            if scrollable
            else (),
        )

    def test_apps_prefers_visible_settings_destination(self):
        snapshot = self._snapshot(text=("Battery", "Apps", "Display"))
        result = resolve_target(
            snapshot,
            "Apps",
            installed_packages=("com.example.apps", "com.google.android.youtube"),
        )
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


if __name__ == "__main__":
    unittest.main()
