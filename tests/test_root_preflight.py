import unittest
from unittest.mock import patch
from types import SimpleNamespace

from nova_agent import _root_preflight


class RootPreflightTests(unittest.TestCase):
    def test_successful_root_preflight(self):
        result = SimpleNamespace(returncode=0, stdout="uid=0(root)", stderr="")
        with patch("nova_agent.run_root", return_value=result) as run_root:
            ready, message = _root_preflight()
        self.assertTrue(ready)
        self.assertIn("Root authorization is ready", message)
        run_root.assert_called_once_with("id", timeout=8.0)

    def test_timeout_explains_visible_magisk_authorization(self):
        result = SimpleNamespace(returncode=124, stdout="", stderr="Command timed out")
        with patch("nova_agent.run_root", return_value=result):
            ready, message = _root_preflight()
        self.assertFalse(ready)
        self.assertIn("Magisk authorization prompt", message)


if __name__ == "__main__":
    unittest.main()
