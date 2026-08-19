from datetime import datetime, timedelta, timezone

from trading_research.contracts import Hypothesis, ResearchGates
from trading_research.experiment import run_experiment
from trading_research.data import Bar


def _write_csv(path):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lines = ["timestamp,open,high,low,close,volume"]
    for index in range(30):
        price = 100.0 + index
        lines.append(
            f"{(start + timedelta(days=index)).isoformat()},{price},{price + 1},{price - 1},{price},1"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_experiment_record_contains_dataset_sha256(tmp_path):
    import hashlib

    csv_path = tmp_path / "bars.csv"
    _write_csv(csv_path)
    hypothesis = Hypothesis(
        name="test",
        thesis="test thesis",
        symbol="EURUSD",
        timeframe="D1",
        rules={"always": "long"},
        expected_edge="test",
        falsifier="test",
    )

    record = run_experiment(
        csv_path=str(csv_path),
        hypothesis=hypothesis,
        signal=lambda _bars, _index: True,
        gates=ResearchGates(minimum_trades=1, minimum_profit_factor=0.1),
    )

    assert record.schema_version == 2
    assert record.dataset_sha256 == hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert record.to_dict()["dataset_sha256"] == record.dataset_sha256
