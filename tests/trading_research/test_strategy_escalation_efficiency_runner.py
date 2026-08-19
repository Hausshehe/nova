from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_strategy_escalation_efficiency_runner(tmp_path: Path) -> None:
    dataset = tmp_path / "bars.csv"
    dataset.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-01-01T00:00:00+00:00,1,1,1,1,1\n"
        "2026-01-01T00:15:00+00:00,1,1,1,1.01,1\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, "tools/run_strategy_escalation_efficiency.py", str(dataset), str(output)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"CLI failed with stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["dataset"] == str(dataset)
    assert output.exists()
