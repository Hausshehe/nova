from datetime import datetime, timedelta, timezone

import hashlib
import json

from trading_research.contracts import Hypothesis, ResearchGates
from trading_research.experiment import run_experiment
from trading_research.memory import ExperienceStore


def _write_csv(path):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lines = ["timestamp,open,high,low,close,volume"]
    for index in range(30):
        price = 100.0 + index
        lines.append(
            f"{(start + timedelta(days=index)).isoformat()},{price},{price + 1},{price - 1},{price},1"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _hypothesis():
    return Hypothesis(
        name="test",
        thesis="test thesis",
        symbol="EURUSD",
        timeframe="D1",
        rules={"always": "long"},
        expected_edge="test",
        falsifier="test",
    )


def test_experiment_record_contains_dataset_sha256(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_csv(csv_path)
    record = run_experiment(
        csv_path=str(csv_path),
        hypothesis=_hypothesis(),
        signal=lambda _bars, _index: True,
        gates=ResearchGates(minimum_trades=1, minimum_profit_factor=0.1),
    )
    assert record.schema_version == 1
    assert record.dataset_sha256 == hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert record.to_dict()["dataset_sha256"] == record.dataset_sha256


def test_run_experiment_persists_and_replays_identically(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_csv(csv_path)
    store = ExperienceStore(tmp_path / "memory.sqlite3")
    kwargs = dict(
        csv_path=str(csv_path),
        hypothesis=_hypothesis(),
        signal=lambda _bars, _index: True,
        gates=ResearchGates(minimum_trades=1, minimum_profit_factor=0.1),
        memory_store=store,
    )

    first = run_experiment(**kwargs)
    second = run_experiment(**kwargs)

    assert first.dataset_sha256 == second.dataset_sha256
    with store._connect() as db:
        rows = db.execute("SELECT experiment_id, record_hash FROM experiments").fetchall()
    assert len(rows) == 1
    assert rows[0]["record_hash"]

    stored = store.get_experiment(rows[0]["experiment_id"])
    assert json.dumps(stored, sort_keys=True) == json.dumps(first.to_dict(), sort_keys=True)
