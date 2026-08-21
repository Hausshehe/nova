from datetime import datetime, timedelta, timezone

from trading_research.contextual_online_expert_ensemble import evaluate_contextual_online_expert_ensemble
from trading_research.data import Bar


def _bars(n=260):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(hours=i),
            open=100 + i * 2.0,
            high=102 + i * 2.0,
            low=98 + i * 2.0,
            close=100 + i * 2.0,
            volume=1.0,
        )
        for i in range(n)
    ]


def test_contextual_ensemble_schema_and_causality_contract():
    result = evaluate_contextual_online_expert_ensemble(
        _bars(), min_global_history=0, min_context_history=0
    )
    assert result["policy"] == "causal_contextual_online_expert_ensemble"
    assert result["candidate_bars"] > 0
    assert result["decisions"] >= 0
    assert set(result["context_decisions"]) == {"uptrend", "downtrend", "global_fallback"}
    assert "future outcomes are evaluation-only" in result["causal_rule"]


def test_invalid_parameters_rejected():
    try:
        evaluate_contextual_online_expert_ensemble(_bars(), half_life=0)
    except ValueError:
        return
    raise AssertionError("invalid half_life should raise ValueError")
