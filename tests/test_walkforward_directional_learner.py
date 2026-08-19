from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.walkforward_directional_learner import evaluate_walkforward_adaptive_direction


def _bars(n=320):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        Bar(start + timedelta(days=i), 100+i*0.01, 100+i*0.02, 99+i*0.0, 100+i*0.01, 1.0)
        for i in range(n)
    )


def test_walkforward_adaptive_direction_is_causal_and_returns_folds():
    result = evaluate_walkforward_adaptive_direction(_bars(), folds=2, min_train=80)
    assert result["policy"] == "causal_walkforward_adaptive_direction"
    assert len(result["fold_net_returns"]) == 2
    assert result["decisions"] >= 0
