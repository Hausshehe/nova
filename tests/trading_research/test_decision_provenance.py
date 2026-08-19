import pytest

from trading_research.decision_provenance import (
    DecisionProvenanceStore,
    TradingDecisionRecord,
)


FP = "a" * 64
DATASET = "b" * 64


def _decision(**overrides):
    values = dict(
        decision_id="D1",
        decided_at_utc="2026-01-01T10:00:00+00:00",
        strategy_name="candidate",
        strategy_version="v1",
        symbol="EURUSD",
        timeframe="1D",
        action="HOLD",
        rationale="Prior evidence was insufficient and risk was above the configured threshold.",
        hypothesis_fingerprint=FP,
        dataset_sha256=DATASET,
        evidence_experiment_ids=("E1", "E2"),
        market_state={"regime": "range", "spread_bps": 1.2},
        risk_snapshot={"risk_per_trade": 0.005, "drawdown": 0.08},
        memory_context={"rejected_count": 4, "independent_count": 1},
        approval_status="NOT_REQUIRED",
    )
    values.update(overrides)
    return TradingDecisionRecord(**values)


def test_decision_provenance_round_trip_and_hashes(tmp_path):
    store = DecisionProvenanceStore(tmp_path / "experience.sqlite3")
    decision = _decision()

    store.record(decision)
    restored = store.get("D1")

    assert restored == decision
    assert len(restored.record_hash) == 64
    assert len(restored.memory_snapshot_hash) == 64


def test_decision_records_are_immutable(tmp_path):
    store = DecisionProvenanceStore(tmp_path / "experience.sqlite3")
    store.record(_decision())

    store.record(_decision())
    with pytest.raises(ValueError, match="different provenance"):
        store.record(_decision(rationale="A materially different reason."))


def test_decision_integrity_failure_is_detected(tmp_path):
    store = DecisionProvenanceStore(tmp_path / "experience.sqlite3")
    store.record(_decision())

    import sqlite3

    with sqlite3.connect(tmp_path / "experience.sqlite3") as db:
        db.execute(
            "UPDATE decision_records SET rationale = ? WHERE decision_id = ?",
            ("tampered", "D1"),
        )
        db.commit()

    with pytest.raises(ValueError, match="decision provenance integrity failure"):
        store.get("D1")


def test_invalid_action_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unsupported decision action"):
        _decision(action="TRUST_ME").validate()


def test_strategy_history_is_chronological(tmp_path):
    store = DecisionProvenanceStore(tmp_path / "experience.sqlite3")
    store.record(_decision(decision_id="D2", decided_at_utc="2026-01-02T10:00:00+00:00"))
    store.record(_decision(decision_id="D1", decided_at_utc="2026-01-01T10:00:00+00:00"))

    assert [item.decision_id for item in store.list_for_strategy("candidate", "v1")] == ["D1", "D2"]
