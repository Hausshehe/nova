from datetime import datetime, timedelta, timezone

from trading_research.contracts import Decision, Hypothesis, ResearchGates
from trading_research.experiment import run_experiment
from trading_research.memory import ExperienceStore


def _write_csv(path, count=240):
    start = datetime(2015, 1, 1, tzinfo=timezone.utc)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("timestamp,open,high,low,close,volume\n")
        for i in range(count):
            price = 100.0 + i * 0.05
            timestamp = start + timedelta(days=i)
            handle.write(
                f"{timestamp.isoformat()},{price},{price + 0.1},{price - 0.1},{price},100\n"
            )


def _hypothesis():
    return Hypothesis(
        name="registry_sync_smoke",
        thesis="A deterministic signal can be recorded as research evidence.",
        symbol="EURUSD",
        timeframe="1D",
        rules={"entry": "always long", "exit": "never until final bar"},
        expected_edge="Positive expectancy in deterministic fixture.",
        falsifier="The research run fails its performance gates.",
    )


def test_experiment_syncs_research_state_but_not_execution_authority(tmp_path):
    csv_path = tmp_path / "fixture.csv"
    _write_csv(csv_path)
    store = ExperienceStore(tmp_path / "experience.sqlite3")

    record = run_experiment(
        csv_path=str(csv_path),
        hypothesis=_hypothesis(),
        signal=lambda bars, index: index >= 1,
        gates=ResearchGates(minimum_trades=1),
        strategy_version="1.0",
        memory_store=store,
    )

    assert record.final_decision == Decision.PROMISING
    saved = store.get_strategy("registry_sync_smoke", "1.0")
    assert saved is not None
    assert saved["status"] == "CANDIDATE"
    assert saved["hypothesis"]["research_state"] == "PROMISING"
    assert saved["approved_at_utc"] is None


def test_experiment_does_not_demote_already_approved_strategy(tmp_path):
    csv_path = tmp_path / "fixture.csv"
    _write_csv(csv_path)
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    store.register_strategy(
        strategy_name="registry_sync_approved",
        strategy_version="1.0",
        status="APPROVED",
        hypothesis={"research_state": "OOS_VALIDATED", "entry": "always long"},
        approved_at_utc="2026-01-01T00:00:00+00:00",
        notes="approved elsewhere",
    )

    run_experiment(
        csv_path=str(csv_path),
        hypothesis=Hypothesis(
            name="registry_sync_approved",
            thesis="A deterministic signal can be recorded as research evidence.",
            symbol="EURUSD",
            timeframe="1D",
            rules={"entry": "always long", "exit": "never until final bar"},
            expected_edge="Positive expectancy in deterministic fixture.",
            falsifier="The research run fails its performance gates.",
        ),
        signal=lambda bars, index: index % 2 == 0,
        gates=ResearchGates(minimum_trades=1),
        strategy_version="1.0",
        memory_store=store,
    )

    saved = store.get_strategy("registry_sync_approved", "1.0")
    assert saved is not None
    assert saved["status"] == "APPROVED"
    assert saved["approved_at_utc"] == "2026-01-01T00:00:00+00:00"
