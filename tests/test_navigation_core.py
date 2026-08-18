import unittest
from unittest.mock import patch
from types import SimpleNamespace

from navigation.actions import ActionResult, activate_node, scroll
from navigation.controller import NavigationController, NavigationState
from navigation.progress import compare_snapshots
from navigation.resolver import resolve_target
from navigation.state import ObservationQuality, Resolution, ScreenSnapshot
from navigation.verifier import VerificationResult, verify_transition


class NavigationCoreTests(unittest.TestCase):
    def _snapshot(self, *, text, package="com.android.settings", scrollable=True, y_offset=0):
        nodes = tuple(
            {
                "text": value,
                "content_description": "",
                "resource_id": "",
                "class": "android.widget.TextView",
                "package": package,
                "bounds": f"[0,{index * 100 + y_offset}][720,{index * 100 + 80 + y_offset}]",
                "clickable": False,
                "enabled": True,
                "focusable": False,
                "actionable_ancestor": {
                    "bounds": f"[0,{index * 100 + y_offset}][720,{index * 100 + 80 + y_offset}]",
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

    def test_small_accessibility_bounds_jitter_is_not_progress(self):
        before = self._snapshot(text=("A", "B", "C"), y_offset=0)
        after = self._snapshot(text=("A", "B", "C"), y_offset=5)
        result = compare_snapshots(before, after)
        self.assertFalse(result.meaningful)

    def test_substantial_stable_node_motion_is_progress(self):
        before = self._snapshot(text=("A", "B", "C"), y_offset=0)
        after = self._snapshot(text=("A", "B", "C"), y_offset=100)
        result = compare_snapshots(before, after)
        self.assertTrue(result.meaningful)
        self.assertIn("moved substantially", result.reason)

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
            result = verify_transition(before, timeout_seconds=0.2, poll_seconds=0)
        self.assertFalse(result.success)
        self.assertIn("target-consistent", result.reason)

    def test_verifier_accepts_meaningful_text_transition(self):
        before = self._snapshot(text=("Apps", "Display", "Battery"))
        after = self._snapshot(text=("App list", "Assistant", "Screen time"))
        with patch("navigation.verifier.observe_screen", return_value=after):
            result = verify_transition(before, timeout_seconds=0.2, poll_seconds=0)
        self.assertTrue(result.success)

    def test_verifier_requires_target_when_requested(self):
        before = self._snapshot(text=("Apps", "Display"))
        unrelated = self._snapshot(text=("Battery", "Storage", "Network"))
        with patch("navigation.verifier.observe_screen", return_value=unrelated):
            result = verify_transition(before, expected_target="Apps", timeout_seconds=0.2, poll_seconds=0)
        self.assertFalse(result.success)
        self.assertFalse(result.target_resolved)

    def test_verifier_accepts_target_on_result_screen(self):
        before = self._snapshot(text=("Settings",))
        after = self._snapshot(text=("Apps", "Display", "Battery"))
        with patch("navigation.verifier.observe_screen", return_value=after):
            result = verify_transition(before, expected_target="Apps", timeout_seconds=0.2, poll_seconds=0)
        self.assertTrue(result.success)
        self.assertTrue(result.target_resolved)

    def test_verifier_accepts_semantic_destination_after_source_disappears(self):
        before = self._snapshot(text=("Apps", "Display", "Battery"))
        after = self._snapshot(text=("App management", "Default apps", "Permissions"))
        with patch("navigation.verifier.observe_screen", return_value=after):
            result = verify_transition(before, expected_target="Apps", timeout_seconds=0.2, poll_seconds=0)
        self.assertTrue(result.success)
        self.assertFalse(result.target_resolved)

    def test_verifier_rejects_unrelated_destination_after_source_disappears(self):
        before = self._snapshot(text=("Apps", "Display", "Battery"))
        after = self._snapshot(text=("Network", "Storage", "Security"))
        with patch("navigation.verifier.observe_screen", return_value=after):
            result = verify_transition(before, expected_target="Apps", timeout_seconds=0.2, poll_seconds=0)
        self.assertFalse(result.success)
        self.assertFalse(result.target_resolved)

    def test_adaptive_scroll_keeps_direction_when_progress_is_real(self):
        first = self._snapshot(text=("A", "B", "C"))
        after_scroll = self._snapshot(text=("D", "E", "F"))
        target_screen = self._snapshot(text=("YouTube", "WhatsApp"))
        controller = NavigationController(observation_retries=1, max_transient_observations=2, max_scrolls=3, settle_seconds=0)
        action = ActionResult(True, "SCROLL", "simulated")
        tap = ActionResult(True, "TAP", "simulated")
        verification = VerificationResult(True, target_screen, "simulated verified transition")
        with patch("navigation.controller.observe_screen", side_effect=[first, after_scroll, target_screen]), patch("navigation.controller.scroll", return_value=action), patch("navigation.controller.activate_node", return_value=tap), patch("navigation.controller.verify_transition", return_value=verification):
            result = controller.navigate_target("YouTube")
        self.assertTrue(result.success)
        self.assertEqual(result.direction, "down")
        self.assertEqual(result.scroll_count, 1)
        self.assertIn(NavigationState.SCROLL, result.history)
        self.assertIn(NavigationState.SUCCESS, result.history)

    def test_activation_verification_failure_gets_one_bounded_retry(self):
        initial = self._snapshot(text=("Apps", "Display"))
        retry_screen = self._snapshot(text=("Apps", "Display"))
        final = self._snapshot(text=("App list", "Assistant"))
        action = ActionResult(True, "TAP", "simulated")
        failed = VerificationResult(False, retry_screen, "simulated delayed transition")
        succeeded = VerificationResult(True, final, "simulated verified transition")
        controller = NavigationController(observation_retries=1, max_activation_retries=1, settle_seconds=0, max_scrolls=0)
        with patch("navigation.controller.observe_screen", side_effect=[initial, retry_screen]), patch("navigation.controller.activate_node", return_value=action) as activate, patch("navigation.controller.verify_transition", side_effect=[failed, succeeded]):
            result = controller.navigate_target("Apps")
        self.assertTrue(result.success)
        self.assertEqual(activate.call_count, 2)
        self.assertEqual(result.history.count(NavigationState.RECOVER), 1)
        self.assertEqual(result.history.count(NavigationState.SUCCESS), 1)

    def test_recovery_accepts_meaningful_destination_without_source_target(self):
        initial = self._snapshot(text=("Apps", "Display", "Battery"))
        destination = self._snapshot(text=("App list", "Assistant", "Screen time"))
        action = ActionResult(True, "TAP", "simulated")
        failed = VerificationResult(False, initial, "simulated delayed transition")
        controller = NavigationController(observation_retries=1, max_activation_retries=1, settle_seconds=0, max_scrolls=0)
        with patch("navigation.controller.observe_screen", side_effect=[initial, destination]), patch("navigation.controller.activate_node", return_value=action), patch("navigation.controller.verify_transition", return_value=failed):
            result = controller.navigate_target("Apps")
        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertEqual(result.state, NavigationState.SUCCESS)
        self.assertIn("during bounded recovery", result.message)

    def test_scroll_command_failures_do_not_trigger_direction_reversal(self):
        snapshot = self._snapshot(text=("A", "B", "C"))
        failed_scroll = ActionResult(False, "SCROLL", "simulated command failure")
        controller = NavigationController(observation_retries=1, max_transient_observations=2, max_scrolls=4, no_progress_before_reversal=2, settle_seconds=0)
        with patch("navigation.controller.observe_screen", return_value=snapshot) as observe, patch("navigation.controller.scroll", return_value=failed_scroll) as scroll:
            result = controller.navigate_target("YouTube")
        self.assertFalse(result.success)
        self.assertEqual(result.direction, "down")
        self.assertEqual(scroll.call_count, 2)
        self.assertGreaterEqual(observe.call_count, 3)
        self.assertIn("refusing to reverse direction", result.message)

    def test_valid_actionable_ancestor_uses_live_center(self):
        node = {"text": "Apps", "enabled": True, "clickable": False, "bounds": "[100,100][200,200]", "actionable_ancestor": {"enabled": True, "clickable": True, "bounds": "[50,50][250,250]"}}
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch("navigation.actions.run_root", return_value=completed) as run_root:
            result = activate_node(node)
            command = run_root.call_args.args[0]
        self.assertTrue(result.success)
        self.assertEqual(command, "input tap 150 150")

    def test_invalid_actionable_ancestor_is_rejected(self):
        node = {"text": "Apps", "enabled": True, "clickable": False, "bounds": "[100,100][200,200]", "actionable_ancestor": {"enabled": True, "clickable": True, "bounds": "[300,300][400,400]"}}
        result = activate_node(node)
        self.assertFalse(result.success)
        self.assertIn("do not contain", result.message)

    def test_scroll_uses_live_region_and_requested_direction(self):
        snapshot = SimpleNamespace(scrollable_regions=({"bounds": "[10,100][710,1500]"},))
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch("navigation.actions.run_root", return_value=completed) as run_root:
            result = scroll(snapshot, "up")
            command = run_root.call_args.args[0]
        self.assertTrue(result.success)
        self.assertEqual(command, "/system/bin/input swipe 360 556 360 1044 691")

    def test_scroll_rejects_invalid_region(self):
        snapshot = SimpleNamespace(scrollable_regions=({"bounds": "invalid"},))
        result = scroll(snapshot, "down")
        self.assertFalse(result.success)
        self.assertIn("invalid live bounds", result.message)

    def test_reversal_requires_two_validated_no_progress_cycles(self):
        first = self._snapshot(text=("A", "B", "C"))
        unchanged1 = self._snapshot(text=("A", "B", "C"))
        unchanged2 = self._snapshot(text=("A", "B", "C"))
        unchanged3 = self._snapshot(text=("A", "B", "C"))
        unchanged4 = self._snapshot(text=("A", "B", "C"))
        unchanged5 = self._snapshot(text=("A", "B", "C"))
        reverse_progress = self._snapshot(text=("D", "E", "F"))
        target_screen = self._snapshot(text=("YouTube",))
        action = ActionResult(True, "SCROLL", "simulated")
        tap = ActionResult(True, "TAP", "simulated")
        verification = VerificationResult(True, target_screen, "simulated verified transition")
        controller = NavigationController(observation_retries=1, max_scrolls=4, no_progress_before_reversal=2, settle_seconds=0)
        with patch("navigation.controller.observe_screen", side_effect=[first, unchanged1, unchanged2, unchanged3, unchanged4, unchanged5, reverse_progress, target_screen, target_screen]), patch("navigation.controller.scroll", return_value=action) as do_scroll, patch("navigation.controller.activate_node", return_value=tap), patch("navigation.controller.verify_transition", return_value=verification):
            result = controller.navigate_target("YouTube")
        self.assertTrue(result.success)
        self.assertEqual(result.direction, "up")
        self.assertGreaterEqual(do_scroll.call_count, 3)
        self.assertIn(NavigationState.SUCCESS, result.history)


if __name__ == "__main__":
    unittest.main()
