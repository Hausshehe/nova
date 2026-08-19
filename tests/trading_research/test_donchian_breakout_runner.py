import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading_research.memory import ExperienceStore
from trading_research.donchian_breakout_runner import main


def _write_csv(path: Path) -> None:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    rows = [["timestamp", "open", "high", "low", "close", "volume"]]
    for index in range(120):
        value = 100.0 + (0.2 * index)
        rows.append([start + timedelta(days=index), value, value, value, value, 1.0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def test_runner_persists_frozen_experiment(tmp_path, monkeypatch):
    csv_path = tmp_path / "bars.csv"
    output_path = tmp_path / "result.json"
    memory_path = tmp_path / "experience.sqlite3"
    _write_csv(csv_path)

    monkeypatch.setattr(
        "sys.argv",
        [
            "donchian_breakout_runner",
            str(csv_path),
            "--output",
            str(output_path),
            "--memory-db",
            str(memory_path),
        ],
    )

    assert main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["hypothesis"]["name"] == "donchian_breakout_55_20_long_only"
    assert payload["costs"] == {
        "fee_bps_per_side": 1.0,
        "slippage_bps_per_side": 1.0,
    }

    store = ExperienceStore(memory_path)
    hypotheses = store.list_experiment_hypotheses()
    assert len(hypotheses) == 1
    assert hypotheses[0]["name"] == "donchian_breakout_55_20_long_only"
