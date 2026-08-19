from trading_research.decision_outcome import DecisionOutcomeRecord, DecisionOutcomeStore
from trading_research.decision_provenance import DecisionProvenanceStore, TradingDecisionRecord
from trading_research.experience_context import TradingExperienceContextBuilder


FP = "a" * 64
DATASET = "b" * 64


def _decision(decision_id, decided_at_utc, *, strategy_name="candidate", strategy_version="v1"):
    return TradingDecisionRecord(
        decision_id=decision_id,
        decided_at_utc=decided_at_utc,
        strategy_name=strategy_name,
        strategy_version=strategy_version,
        symbol="EURUSD",
        timeframe="1D",
        action="BUY",
        rationale="bounded test decision",
        hypothesis_fingerprint=FP,
        dataset_sha256=DATASET,
        evidence_experiment_ids=(),
        market_state={"regime": "range"},
        risk_snapshot={"risk_per_trade": 0.005},
    )


def _outcome(outcome_id, decision_id, recorded_at_utc, trade_id=None):
    return DecisionOutcomeRecord(
        outcome_id=outcome_id,
        decision_id=decision_id,
        trade_id=trade_id or outcome_id,
        recorded_at_utc=recorded_at_utc,
        outcome="WIN",
        realized_pnl=10.0,
        attribution="DECISION",
        lesson="bounded historical lesson",
        execution_summary={"slippage_bps": 1.0},
    )


def _stores(tmp_path):
    return (
        DecisionProvenanceStore(tmp_path / "decisions.sqlite3"),
        DecisionOutcomeStore(tmp_path / "outcomes.sqlite3"),
    )


def test_context_excludes_future_decisions_and_outcomes(tmp_path):
    decisions, outcomes = _stores(tmp_path)
    decisions.record(_decision("D1", "2026-01-01T10:00:00+00:00"))
    decisions.record(_decision("D2", "2026-01-04T10:00:00+00:00"))
    outcomes.record(_outcome("O1", "D1", "2026-01-02T10:00:00+00:00"))
    outcomes.record(_outcome("O2", "D1", "2026-01-04T12:00:00+00:00"))

    context = TradingExperienceContextBuilder(decisions, outcomes).build(
        strategy_name="candidate",
        strategy_version="v1",
        as_of_utc="2026-01-04T10:00:00+00:00",
    )

    assert [item["decision_id"] for item in context.prior_decisions] == ["D1"]
    assert [item["outcome_id"] for item in context.prior_outcomes] == ["O1"]


def test_context_is_scoped_to_strategy_and_version(tmp_path):
    decisions, outcomes = _stores(tmp_path)
    decisions.record(_decision("D1", "2026-01-01T10:00:00+00:00", strategy_name="other"))
    decisions.record(_decision("D2", "2026-01-02T10:00:00+00:00", strategy_version="v2"))
    decisions.record(_decision("D3", "2026-01-03T10:00:00+00:00"))

    context = TradingExperienceContextBuilder(decisions, outcomes).build(
        strategy_name="candidate",
        strategy_version="v1",
        as_of_utc="2026-01-04T00:00:00+00:00",
    )

    assert [item["decision_id"] for item in context.prior_decisions] == ["D3"]


def test_context_limits_and_hash_are_stable(tmp_path):
    decisions, outcomes = _stores(tmp_path)
    for index in range(3):
        decisions.record(_decision(f"D{index}", f"2026-01-0{index + 1}T10:00:00+00:00"))
        outcomes.record(_outcome(f"O{index}", f"D{index}", f"2026-01-0{index + 1}T12:00:00+00:00"))

    builder = TradingExperienceContextBuilder(decisions, outcomes)
    first = builder.build(
        strategy_name="candidate",
        strategy_version="v1",
        as_of_utc="2026-01-04T00:00:00+00:00",
        max_decisions=2,
        max_outcomes=1,
    )
    second = builder.build(
        strategy_name="candidate",
        strategy_version="v1",
        as_of_utc="2026-01-04T00:00:00+00:00",
        max_decisions=2,
        max_outcomes=1,
    )

    assert len(first.prior_decisions) == 2
    assert len(first.prior_outcomes) == 1
    assert first.context_hash == second.context_hash
