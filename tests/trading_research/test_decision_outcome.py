import sqlite3

import pytest

from trading_research.decision_outcome import DecisionOutcomeRecord, DecisionOutcomeStore


def _outcome(**overrides):
    values = dict(
        outcome_id="O1",
        decision_id="D1",
        trade_id="T1",
        recorded_at_utc="2026-01-02T10:00:00+00:00",
        outcome="WIN",
        realized_pnl=12.5,
        attribution="EXECUTION",
        lesson="The decision was sound; execution added modest slippage.",
        execution_summary={"slippage_bps": 1.2, "latency_ms": 180},
    )
    values.update(overrides)
    return DecisionOutcomeRecord(**values)


def test_outcome_round_trip_and_hash(tmp_path):
    store = DecisionOutcomeStore(tmp_path / "experience.sqlite3")
    outcome = _outcome()

    store.record(outcome)
    assert store.get("O1") == outcome
    assert len(outcome.record_hash) == 64


def test_outcome_is_idempotent_but_immutable(tmp_path):
    store = DecisionOutcomeStore(tmp_path / "experience.sqlite3")
    outcome = _outcome()
    store.record(outcome)
    store.record(outcome)

    with pytest.raises(ValueError, match="different evidence"):
        store.record(_outcome(lesson="changed"))


def test_one_decision_trade_pair_cannot_be_relinked(tmp_path):
    store = DecisionOutcomeStore(tmp_path / "experience.sqlite3")
    store.record(_outcome())

    with pytest.raises(ValueError, match="already linked"):
        store.record(_outcome(outcome_id="O2"))


def test_tampering_is_detected(tmp_path):
    path = tmp_path / "experience.sqlite3"
    store = DecisionOutcomeStore(path)
    store.record(_outcome())

    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE decision_outcomes SET lesson = ? WHERE outcome_id = ?",
            ("tampered", "O1"),
        )
        db.commit()

    with pytest.raises(ValueError, match="integrity failure"):
        store.get("O1")


def test_invalid_outcome_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unsupported realized outcome"):
        _outcome(outcome="UNKNOWN").validate()


def test_list_for_decision_is_chronological(tmp_path):
    store = DecisionOutcomeStore(tmp_path / "experience.sqlite3")
    store.record(_outcome(outcome_id="O2", trade_id="T2", recorded_at_utc="2026-01-03T10:00:00+00:00"))
    store.record(_outcome(outcome_id="O1", trade_id="T1", recorded_at_utc="2026-01-02T10:00:00+00:00"))

    assert [item.outcome_id for item in store.list_for_decision("D1")] == ["O1", "O2"]
