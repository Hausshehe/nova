import unittest
from unittest.mock import patch

from navigation.actions import ActionResult
from navigation.state import ScreenSnapshot
from tools.diagnose_navigation import run_one_scroll


class NavigationDiagnosticProbeTests(unittest.TestCase):
    def _snapshot(self, text):
        nodes = tuple(
            {
                "text": value,
                "content_description": "",
                "resource_id": "",
                "class": "android.widget.TextView",
                "package": "com.android.settings",
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
            foreground_package="com.android.settings",
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
        ) as scroll, patch("tools.diagnose_navigation.resolve_target") as resolve:
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

        comparison = next(event for event in events if event["stage"] == "observation_comparison")
        self.assertTrue(comparison["semantic_signature_changed"])

        final_decision = events[-1]
        self.assertEqual(final_decision["event"], "activation_ready")
        self.assertEqual(final_decision["action"], "ACTIVATE_NOT_PERFORMED_BY_PROBE")


if __name__ == "__main__":
    unittest.main()
