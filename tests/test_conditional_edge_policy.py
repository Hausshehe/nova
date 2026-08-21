from datetime import datetime, timedelta, timezone

from trading_research.conditional_edge_policy import CONTEXTS, evaluate_conditional_edge_gate
from trading_research.data import Bar


def _bars(n=420, step=0.5):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(hours=i),
            open=100 + i * step,
            high=101 + i * step,
            low=99 + i * step,
            close=100 + i * step,
            volume=1.0,
        )
        for i in range(n)
    ]


def test_schema_and_causality_contract():
    bars = _bars()
    result = evaluate_conditional_edge_gate(
        bars,
        min_global_history=0,
        min_context_history=0,
    )
    assert result["policy"] == "causal_conditional_edge_gate"
    assert result["candidate_bars"] == len(bars) - 99
    assert result["decisions"] >= 0
    assert result["abstentions"] >= 0
    assert set(result["contexts"]) == set(CONTEXTS)
    assert "after its horizon completes" in result["causal_rule"]


def test_future_tail_cannot_change_earlier_decision_set():
    base = _bars(460)
    altered = list(base)
    for i in range(430, 460):
        old = altered[i]
        altered[i] = Bar(
            timestamp=old.timestamp,
            open=old.open,
            high=old.high,
            low=old.low,
            close=old.close + 10_000.0,
            volume=old.volume,
        )

    kwargs = dict(
        min_global_history=20,
        min_context_history=10,
        z_score=1.0,
        min_edge_bps=0.5,
        min_margin_bps=0.5,
        folds=4,
    )
    left = evaluate_conditional_edge_gate(base, **kwargs)
    right = evaluate_conditional_edge_gate(altered, **kwargs)

    left_prefix = [row for row in left.get("predictions", []) if row["index"] < 430]
    right_prefix = [row for row in right.get("predictions", []) if row["index"] < 430]
    assert left_prefix == right_prefix


def test_strict_gate_can_abstain_everywhere():
    result = evaluate_conditional_edge_gate(
        _bars(),
        min_global_history=20,
        min_context_history=10,
        min_edge_bps=1e9,
        min_margin_bps=1e9,
    )
    assert result["decisions"] == 0
    assert result["abstentions"] == result["candidate_bars"]


def test_invalid_parameters_rejected():
    bars = _bars(320)
    invalid = [
        {"half_life": 0},
        {"min_edge_bps": -1},
        {"min_margin_bps": -1},
        {"folds": 0},
        {"evaluation_start_index": len(bars) + 1},
    ]
    for kwargs in invalid:
        try:
            evaluate_conditional_edge_gate(bars, **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {kwargs}")
