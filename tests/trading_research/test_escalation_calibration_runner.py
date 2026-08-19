from pathlib import Path

from tools.run_escalation_calibration import main


def test_runner_module_is_importable() -> None:
    assert callable(main)
