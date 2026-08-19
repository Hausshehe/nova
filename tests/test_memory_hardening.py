import json

import pytest

from trading_research.memory import ExperienceStore
from trading_research.strategy_registry import Strategy, StrategyRegistry


def _experiment_record() -> dict:
    return {
        "schema_version": 1,
        "hypothesis": {
            "name": "test-strategy",
            "thesis": "test",
            "symbol": "EURUSD",
            "timeframe": "D1",
            "rules": {"direction": "long"},
            "expected_edge": "test edge",
            "falsifier": "negative test",
            "rationale": "unit test",
        },
        "dataset": "missing-dataset.csv",
    }


def test_experiment_record_is_idempotent_but_not_replaceable(tmp_path):
    store = ExperienceStore(tmp_path / "memory.sqlite")
    record = _experiment_record()
    store.record_experiment(
        experiment_id="exp-1",
        created_at_utc="2026-01-01T00:00:00+00:00",
        hypothesis_name="test-strategy",
        symbol="EURUSD",
        timeframe="D1",
        final_decision="REJECT",
        record=record,
    )

    store.record_experiment(
        experiment_id="exp-1",
        created_at_utc="2026-01-01T00:00:00+00:00",
        hypothesis_name="test-strategy",
        symbol="EURUSD",
        timeframe="D1",
        final_decision="REJECT",
        record=record,
    )

    changed = dict(record)
    changed["note"] = "tampered"
    with pytest.raises(ValueError, match="different evidence"):
        store.record_experiment(
            experiment_id="exp-1",
            created_at_utc="2026-01-01T00:00:00+00:00",
            hypothesis_name="test-strategy",
            symbol="EURUSD",
            timeframe="D1",
            final_decision="PROMISING",
            record=changed,
        )


def test_experiment_provenance_and_integrity_are_queryable(tmp_path):
    store = ExperienceStore(tmp_path / "memory.sqlite")
    record = _experiment_record()
    store.record_experiment(
        experiment_id="exp-1",
        created_at_utc="2026-01-01T00:00:00+00:00",
        hypothesis_name="test-strategy",
        symbol="EURUSD",
        timeframe="D1",
        final_decision="REJECT",
        record=record,
    )

    assert store.get_experiment("exp-1")["hypothesis"]["name"] == "test-strategy"
    assert store.list_experiment_hypotheses()[0]["name"] == "test-strategy"

    with store._connect() as db:
        row = db.execute(
            "SELECT hypothesis_fingerprint, record_hash FROM experiments WHERE experiment_id = ?",
            ("exp-1",),
        ).fetchone()
    assert row["hypothesis_fingerprint"]
    assert row["record_hash"]


def test_experiment_tampering_is_detected(tmp_path):
    path = tmp_path / "memory.sqlite"
    store = ExperienceStore(path)
    record = _experiment_record()
    store.record_experiment(
        experiment_id="exp-1",
        created_at_utc="2026-01-01T00:00:00+00:00",
        hypothesis_name="test-strategy",
        symbol="EURUSD",
        timeframe="D1",
        final_decision="REJECT",
        record=record,
    )

    with store._connect() as db:
        db.execute(
            "UPDATE experiments SET record_json = ? WHERE experiment_id = ?",
            (json.dumps({"tampered": True}), "exp-1"),
        )

    with pytest.raises(ValueError, match="integrity failure"):
        store.get_experiment("exp-1")


def test_strategy_registry_can_read_and_update_strategy(tmp_path):
    store = ExperienceStore(tmp_path / "memory.sqlite")
    registry = StrategyRegistry(store)
    strategy = Strategy(
        name="test-strategy",
        version="1.0",
        status="CANDIDATE",
        research_state="RESEARCH",
        hypothesis={"symbol": "EURUSD", "timeframe": "D1"},
    )
    registry.register(strategy)

    loaded = store.get_strategy("test-strategy", "1.0")
    assert loaded is not None
    assert loaded["status"] == "CANDIDATE"

    registry.set_research_state("test-strategy", "1.0", "REJECTED", "test result")
    assert store.get_strategy("test-strategy", "1.0")["hypothesis"]["research_state"] == "REJECTED"
