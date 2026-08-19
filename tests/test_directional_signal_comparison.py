from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.directional_signal_comparison import compare_directional_signals


def _bars(n: int = 80) -> list[Bar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = [1.0 + i * 0.001 for i in range(n)]
    return [
        Bar(start + timedelta(days=i), c, c, c, c, 1.0)
        for i, c in enumerate(closes)
    ]


def test_comparison_returns_predefined_signals_only():
    results = compare_directional_signals(_bars(), future_bars=4, folds=4)
    assert [r.signal for r in results] == ["sma20_50", "momentum4", "momentum8", "momentum12"]
    assert all(len(r.chronological_fold_net_returns) == 4 for r in results)


def test_comparison_rejects_invalid_horizon():
    try:
        compare_directional_signals(_bars(), future_bars=0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
