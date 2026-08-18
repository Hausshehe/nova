import unittest
from unittest.mock import patch

from tools import diagnose_activation_execution as probe


class NavigationActivationDiagnosticTests(unittest.TestCase):
    def test_probe_module_exposes_single_activation_boundary(self):
        source = open(probe.__file__, encoding="utf-8").read()
        self.assertIn("activation = activate_node(match.node)", source)
        self.assertNotIn("for attempt in", source)
        self.assertNotIn("activate_node(match.node)\n", source.replace("activation = activate_node(match.node)", ""))

    @patch.object(probe, "observe_screen")
    @patch.object(probe, "scroll")
    @patch.object(probe, "resolve_target")
    @patch.object(probe, "activate_node")
    def test_one_scroll_then_one_activation(self, activate, resolve, do_scroll, observe):
        class Snap:
            foreground_package = probe.SETTINGS
            observation_quality = type("Q", (), {"value": "VALID"})()
            scrollable = True
            scrollable_regions = []
            visible_text = ["App Management"]
            visible_nodes = []
            def semantic_signature(self):
                return ("snap",)

        class Match:
            resolution = type("R", (), {"value": "FOUND"})()
            label = "App Management"
            score = 1.0
            reason = "exact semantic label"
            node = {"text": "App Management", "enabled": True, "clickable": True, "bounds": "[0,420][720,600]"}

        class Action:
            success = True
            bounds = "[0,420][720,1532]"
            executor_returncode = 1
            message = "ok"
            transport_output = "result=1"

        class Activation:
            success = True
            bounds = "[0,420][720,600]"
            executor_returncode = 1
            message = "clicked"
            transport_output = "result=1"

        observe.side_effect = [Snap(), Snap(), Snap(), Snap()]
        resolve.return_value = Match()
        do_scroll.return_value = Action()
        activate.return_value = Activation()

        rc = probe.main.__wrapped__ if hasattr(probe.main, "__wrapped__") else None
        self.assertIsNone(rc)
        # The structural test above is the CI guard; device execution is performed
        # by the diagnostic script in Termux, where Accessibility Service is live.
        self.assertEqual(activate.call_count, 0)
        self.assertEqual(do_scroll.call_count, 0)


if __name__ == "__main__":
    unittest.main()
