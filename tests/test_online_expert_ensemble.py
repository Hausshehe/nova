from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.online_expert_ensemble import evaluate_online_expert_ensemble, EXPERTS


def _bars(n=700):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(hours=i),
            open=100 + i * 0.1,
            high=101 + i * 0.1,
            low=99 + i * 0.1,
            close=100 + i * 0.1,
            volume=1.0,
        )
        for i in range(n)
    ]


def test_online_expert_ensemble_returns_causal_report():
    bars = _bars()
    result = evaluate_online_expert_ensemble(bars, folds=4)
    assert result["policy"] == "causal_online_expert_ensemble"
    assert tuple(result["experts"]) == EXPERTS
    assert len(result["fold_net_returns"]) == 4
    assert result["candidate_bars"] == len(bars) - 49
    assert "after its horizon fully elapsed" in result["causal_rule"]


def test_evaluation_start_preserves_prior_history():
    bars = _bars()
    result = evaluate_online_expert_ensemble(
        bars,
        min_history=20,
        evaluation_start_index=500,
        folds=4,
    )
    assert result["candidate_bars"] == len(bars) - 500
    assert all(row["index"] >= 500 for row in result["predictions"])
