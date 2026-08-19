import csv
from pathlib import Path

from trading_research.memory import ExperienceStore
from trading_research.volatility_mean_reversion_runner import main


def _write_csv(path: Path) -> None:
    rows = [
        ["timestamp", "open", "high", "low", "close", "volume"],
    ]
    base = 100.0
    for index in range(80):
        value = base if index < 60 else base - (index - 59) * 2.0
        rows.append([
            f"2020-01-{index + 1:02d}T00:00:00+00:00",
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

    store = ExperienceStore(memory_path)
    experiments = store.list_experiments_for_hypothesis(
        store.list_experiment_hypotheses()[0]["name"]
        and next(iter(
            store.list_experiments_for_hypothesis(
                __import__("trading_research.memory", fromlist=["_fingerprint_hypothesis"])._fingerprint_hypothesis(
                    store.list_experiment_hypotheses()[0]
                )
            )
        ))
        .get("hypothesis", {})
        .get("fingerprint", "")
    )
    assert experiments
