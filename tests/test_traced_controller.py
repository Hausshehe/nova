import unittest
from unittest.mock import patch

from navigation.controller import NavigationController, NavigationState, NavigationResult
from navigation.diagnostics import DiagnosticTrace
from navigation.traced_controller import TracedNavigationController


class TracedNavigationControllerTests(unittest.TestCase):
    def _result(self, success=True):
        return NavigationResult(
            success=success,
            verified=success,
            target="Apps",
            state=NavigationState.SUCCESS if success else NavigationState.FAILURE,
            message="ok" if success else "failed",
            history=(NavigationState.START, NavigationState.SUCCESS)
            if success
            else (NavigationState.START, NavigationState.FAILURE),
        )

    def test_wrapper_preserves_underlying_result(self):
        trace = DiagnosticTrace(enabled=True)
        expected = self._result(True)
        with patch.object(NavigationController, "navigate_target", return_value=expected):
            wrapper = TracedNavigationController(trace=trace)
            actual = wrapper.navigate_target("Apps")

        self.assertIs(actual, expected)
        names = [event["name"] for event in trace.to_dict()["events"]]
        self.assertIn("navigate_target", names)
        self.assertIn("controller_start", names)
        self.assertIn("SUCCESS", names)
        self.assertIn("navigation_success", names)

    def test_failure_is_recorded_without_changing_result(self):
        trace = DiagnosticTrace(enabled=True)
        expected = self._result(False)
        with patch.object(NavigationController, "navigate_target", return_value=expected):
            wrapper = TracedNavigationController(trace=trace)
            actual = wrapper.navigate_target("Apps")

        self.assertIs(actual, expected)
        failures = [
            event for event in trace.to_dict()["events"]
            if event["kind"] == "failure"
        ]
        self.assertEqual(failures[-1]["name"], "navigation_failure")

    def test_disabled_trace_does_not_change_execution(self):
        trace = DiagnosticTrace(enabled=False)
        expected = self._result(True)
        with patch.object(NavigationController, "navigate_target", return_value=expected) as navigate:
            wrapper = TracedNavigationController(trace=trace)
            actual = wrapper.navigate_target("Apps")

        self.assertIs(actual, expected)
        navigate.assert_called_once()
        self.assertEqual(trace.to_dict(), {"enabled": False, "events": []})


if __name__ == "__main__":
    unittest.main()
