import unittest

from navigation.recovery import run_bounded_recovery
from navigation.state import ObservationQuality, ScreenSnapshot


class NavigationRecoveryBoundedTests(unittest.TestCase):
    def test_transient_state_gets_one_recovery_action(self):
        calls = {"initial": 0, "recovery": 0, "observe": 0}

        def initial():
            calls["initial"] += 1
            return "initial"

        def observe(_previous):
            calls["observe"] += 1
            if calls["observe"] == 1:
                return ScreenSnapshot(
                    foreground_package="com.android.settings",
                    visible_text=("Bluetooth",),
                    observation_quality=ObservationQuality.VALID,
                )
            return ScreenSnapshot(
                foreground_package="com.android.settings",
                visible_text=("Settings", "Search settings"),
                observation_quality=ObservationQuality.VALID,
            )

        def recovery(_snapshot):
            calls["recovery"] += 1
            return "recovered"

        result = run_bounded_recovery(
            initial_action=initial,
            observe=observe,
            success_predicate=lambda snapshot: "Search settings" in snapshot.visible_text,
            recovery_action=recovery,
        )

        self.assertTrue(result.success)
        self.assertEqual(calls["initial"], 1)
        self.assertEqual(calls["recovery"], 1)
        self.assertEqual(calls["observe"], 2)
        self.assertEqual(result.observations, 2)
        self.assertEqual(result.recovery_actions, 1)

    def test_recovery_is_never_repeated_beyond_budget(self):
        calls = {"initial": 0, "recovery": 0, "observe": 0}

        def initial():
            calls["initial"] += 1
            return "initial"

        def observe(_previous):
            calls["observe"] += 1
            return ScreenSnapshot(
                foreground_package="com.android.settings",
                visible_text=("Bluetooth",),
                observation_quality=ObservationQuality.VALID,
            )

        def recovery(_snapshot):
            calls["recovery"] += 1
            return "recovered"

        result = run_bounded_recovery(
            initial_action=initial,
            observe=observe,
            success_predicate=lambda _snapshot: False,
            recovery_action=recovery,
            max_observations=2,
            max_recovery_actions=1,
        )

        self.assertFalse(result.success)
        self.assertEqual(calls["initial"], 1)
        self.assertEqual(calls["observe"], 2)
        self.assertEqual(calls["recovery"], 1)
        self.assertEqual(result.observations, 2)
        self.assertEqual(result.recovery_actions, 1)


if __name__ == "__main__":
    unittest.main()
