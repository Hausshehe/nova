import json
import unittest
from unittest.mock import patch

from navigation.diagnostics import DiagnosticTrace


class NavigationDiagnosticsTests(unittest.TestCase):
    def test_disabled_trace_is_noop(self):
        trace = DiagnosticTrace(enabled=False)
        trace.record("decision", "ignored", value=1)
        self.assertEqual(trace.to_dict(), {"enabled": False, "events": []})
        self.assertEqual(trace.render(), "Diagnostics disabled.")

    def test_trace_records_relative_timing_and_action_duration(self):
        trace = DiagnosticTrace(enabled=True)
        with patch(
            "navigation.diagnostics.time.monotonic",
            side_effect=[10.0, 10.0, 10.125, 10.125],
        ):
            trace.record("goal", "start", goal="Open Settings")
            trace.start_action("a1", "scroll", direction="down")
            trace.end_action("a1", "scroll", success=True)

        data = trace.to_dict()
        self.assertTrue(data["enabled"])
        self.assertEqual(data["events"][0]["kind"], "goal")
        self.assertEqual(data["events"][1]["kind"], "action_start")
        self.assertEqual(data["events"][2]["duration_ms"], 125.0)

    def test_render_is_human_readable_and_json_safe(self):
        trace = DiagnosticTrace(enabled=True)
        trace.decision("resolve_target", label="Apps", node={"bounds": "[0,0][100,100]"})
        rendered = trace.render()
        self.assertIn("NOVA TRACE", rendered)
        self.assertIn("resolve_target", rendered)
        json.dumps(trace.to_dict())

    def test_failure_event_is_distinct(self):
        trace = DiagnosticTrace(enabled=True)
        trace.failure("verification_timeout", target="Apps", elapsed_ms=3100)
        event = trace.to_dict()["events"][0]
        self.assertEqual(event["kind"], "failure")
        self.assertEqual(event["name"], "verification_timeout")


if __name__ == "__main__":
    unittest.main()
