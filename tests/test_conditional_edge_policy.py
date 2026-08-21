from datetime import datetime, timedelta, timezone

from trading_research.conditional_edge_policy import CONTEXTS, evaluate_conditional_edge_gate
from trading_research.data import Bar


def _bars(n=320):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(hours=i),
            open=100 + i * 0.5,
            high=101 + i * 0.5,
            low=99 + i * 0.5,
            close=100 + i * 0.5,
            volume=1.0,
        )
        for i in range(n)
    ]


def test_conditional_edge_schema_and_causality_contract():
    result = evaluate_conditional_edge_gate(
        _bars(), min_global_history=0, min_context_history=0
    )
    assert result["policy"] == "causal_conditional_edge_gate"
    assert result["candidate_bars"] > 0
    assert result["decisions"] >= 0
    assert result["abstentions"] >= 0
    assert set(result["contexts"]) == set(CONTEXTS)
    assert "Completed outcomes are incorporated only after their horizon completes" in result["causal_rule"]


def test_invalid_parameters_rejected():
    try:
        evaluate_conditional_edge_gate(_bars(), min_edge_bps=-1)
    except ValueError:
        return
    raise AssertionError("negative min_edge_bps should raise ValueError")
