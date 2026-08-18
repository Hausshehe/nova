import unittest
from unittest.mock import patch

from navigation.actions import ActionResult
from navigation.state import ScreenSnapshot
from tools.diagnose_navigation import _launch_settings, run_one_scroll


class NavigationDiagnosticProbeTests(unittest.TestCase):
    def _snapshot(self, text, package="com.android.settings"):
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
                "scrollable": False,
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
            scrollable_regions=({"bounds": "[0,212][720,1452]"},),
        )

    def test_probe_records_before_scroll_and_fresh_after_scroll_resolution(self):
        before = self._snapshot(("Battery", "Display"))
        after = self._snapshot(("Battery", "Apps"))
        scroll_result = ActionResult(
            True,
            "SCROLL",
            "simulated",
            "[0,212][720,1452]",
            147.2,
            0,
            "Broadcast completed: result=1",
        )

        with patch(
            "tools.diagnose_navigation.observe_screen",
            side_effect=[before, after],
        ), patch(
            "tools.diagnose_navigation.scroll",
            return_value=scroll_result,
        ) as scroll, patch("tools.diagnose_navigation.resolve_target") as resolve, patch(
            "tools.diagnose_navigation._snapshot_timestamp_ms",
            side_effect=[1000, 1001],
        ):
            from navigation.resolver import resolve_target as real_resolve

            resolve.side_effect = [
                real_resolve(before, "Apps"),
                real_resolve(after, "Apps"),
            ]
            trace = run_one_scroll("Apps")

        events = trace.events
        self.assertEqual(scroll.call_count, 1)
        self.assertEqual(
            [event["event"] for event in events if event["stage"] == "observation"],
            ["before_scroll", "after_scroll"],
        )
        self.assertEqual(
            [event["event"] for event in events if event["stage"] == "target_resolution"],
            ["before_scroll", "after_scroll"],
        )

        transport = next(event for event in events if event["stage"] == "scroll_request")
        self.assertEqual(transport["executor_returncode"], 0)
        self.assertEqual(transport["duration_ms"], 147.2)
        self.assertEqual(transport["transport_output"], "Broadcast completed: result=1")
        self.assertEqual(transport["before_snapshot_timestamp_ms"], 1000)

        comparison = next(event for event in events if event["stage"] == "observation_comparison")
        self.assertTrue(comparison["semantic_signature_changed"])

        final_decision = events[-1]
        self.assertEqual(final_decision["event"], "activation_ready")
        self.assertEqual(final_decision["action"], "ACTIVATE_NOT_PERFORMED_BY_PROBE")

    def test_probe_stops_when_no_new_snapshot_is_published(self):
        before = self._snapshot(("Battery", "Display"))
        scroll_result = ActionResult(
            True,
            "SCROLL",
            "simulated",
            "[0,212][720,1452]",
            147.2,
            0,
            "Broadcast completed: result=1",
        )

        with patch("tools.diagnose_navigation.observe_screen", return_value=before), patch(
            "tools.diagnose_navigation.scroll", return_value=scroll_result
        ) as scroll, patch(
            "tools.diagnose_navigation._snapshot_timestamp_ms", return_value=1000
        ), patch("tools.diagnose_navigation.time.sleep"):
            trace = run_one_scroll("Apps")

        self.assertEqual(scroll.call_count, 1)
        self.assertEqual(trace.events[-1]["event"], "post_scroll_observation_timeout")
        self.assertEqual(trace.events[-1]["stage"], "failure")

    def test_launch_settings_waits_for_settings_foreground(self):
        trace_snapshots = [
            self._snapshot(("Terminal",), package="com.termux"),
            self._snapshot(("Settings",), package="com.android.settings"),
        ]
        completed = type(
            "R",
            (),
            {
                "returncode": 0,
                "stdout": "Starting: Intent { act=android.settings.SETTINGS }",
                "stderr": "",
            },
        )()
        with patch("tools.diagnose_navigation.subprocess.run", return_value=completed) as run, patch(
            "tools.diagnose_navigation.observe_screen", side_effect=trace_snapshots
        ), patch("tools.diagnose_navigation.time.sleep"):
            trace = type("T", (), {"events": []})()
            self.assertTrue(_launch_settings(trace, timeout_seconds=1.0))

        self.assertEqual(run.call_args.args[0], ["am", "start", "-a", "android.settings.SETTINGS"])
        self.assertEqual(
            [event["event"] for event in trace.events],
            ["launch_settings", "settings_foreground_confirmed"],
        )
        self.assertEqual(trace.events[-1]["package"], "com.android.settings")


if __name__ == "__main__":
    unittest.main()
