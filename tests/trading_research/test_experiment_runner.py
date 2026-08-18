from datetime import datetime, timedelta, timezone

from trading_research.contracts import Decision, Hypothesis, ResearchGates
from trading_research.experiment import run_experiment


def _write_csv(path, count=240, slope=0.05):
    start = datetime(2015, 1, 1, tzinfo=timezone.utc)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("timestamp,open,high,low,close,volume\n")
        for i in range(count):
            price = 100.0 + i * slope
            timestamp = start + timedelta(days=i)
            handle.write(
                f"{timestamp.isoformat()},{price},{price + 0.1},{price - 0.1},{price},100\n"
            )


def _hypothesis():
    return Hypothesis(
        name="runner-smoke",
        thesis="A deterministic test signal can be evaluated reproducibly.",
        symbol="EURUSD",
        timeframe="1D",
        rules={"entry": "always long", "exit": "never until final bar"},
        expected_edge="Positive expectancy in deterministic fixture.",
        falsifier="The held-out experiment fails its performance gates.",
    )


def test_runner_produces_standardized_three_segment_record(tmp_path):
    csv_path = tmp_path / "fixture.csv"
    _write_csv(csv_path, slope=0.05)

    def signal(bars, index):
        return index >= 1

    record = run_experiment(
        csv_path=str(csv_path),
        hypothesis=_hypothesis(),
        signal=signal,
        gates=ResearchGates(minimum_trades=1),
        fee_bps=1.0,
        slippage_bps=1.0,
    )

    payload = record.to_dict()
    assert record.schema_version == 1
    assert record.total_bars == 240
    assert record.split_sizes == {"train": 144, "validation": 48, "test": 48}
    assert [segment.name for segment in record.segments] == ["train", "validation", "test"]
    assert record.final_decision == Decision.PROMISING
    assert payload["final_decision"] == "PROMISING"


def test_runner_rejects_when_a_segment_has_real_performance_failure(tmp_path):
    csv_path = tmp_path / "fixture.csv"
    _write_csv(csv_path, slope=-0.05)

    def always_long(bars, index):
        return index >= 1

    record = run_experiment(
        csv_path=str(csv_path),
        hypothesis=_hypothesis(),
        signal=always_long,
        gates=ResearchGates(minimum_trades=1),
    )

    assert record.final_decision == Decision.REJECT
    assert any(segment.decision.decision == Decision.REJECT for segment in record.segments)
