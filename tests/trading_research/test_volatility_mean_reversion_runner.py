import csv
import json
import sqlite3
from pathlib import Path

from trading_research.memory import ExperienceStore
from trading_research.volatility_mean_reversion_runner import main


def _write_csv(path: Path) -> None:
    rows = [["timestamp", "open", "high", "low", "close", "volume"]]
    base = 100.0
    for index in range(80):
        value = base if index < 60 else base - (index - 59) * 2.0
        rows.append([
            f"2020-02-{index + 1:02d}T00:00:00+00:00",
            value,
            value,
            value,
            value,
            1.0,
        ])
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def test_runner_persists_experiment_memory(tmp_path, monkeypatch):
    csv_path = tmp_path / "bars.csv"
    output_path = tmp_path / "result.json"
    memory_path = tmp_path / "experience.sqlite3"
    _write_csv(csv_path)

    monkeypatch.setattr(
        "sys.argv",
        [
            "volatility_mean_reversion_runner",
            str(csv_path),
            "--output",
            str(output_path),
            "--memory-db",
            str(memory_path),
        ],
    )

    assert main() == 0
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["dataset_sha256"]
    assert payload["costs"] == {
        "fee_bps_per_side": 2.0,
        "slippage_bps_per_side": 2.0,
    }

    with sqlite3.connect(memory_path) as db:
        count = db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    assert count == 1

    store = ExperienceStore(memory_path)
    hypothesis = store.list_experiment_hypotheses()[0]
    assert hypothesis["name"] == "volatility_normalized_mean_reversion_20_2z"
