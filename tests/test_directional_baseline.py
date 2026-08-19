from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.directional_baseline import build_directional_outcomes, summarize_directional_outcomes


def _bars(closes):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        Bar(base + timedelta(days=i), value, value + 0.5, value - 0.5, value, 100.0)
        for i, value in enumerate(closes)
    )


def test_directional_baseline_uses_only_history_for_direction():
    bars = _bars([100 + i for i in range(60)])
    outcomes = build_directional_outcomes(bars, future_bars=4, fast_period=3, slow_period=5)
    assert outcomes
    assert all(item.direction == "LONG" for item in outcomes)
    assert all(item.index >= 4 for item in outcomes)


def test_directional_summary_is_deterministic():
    bars = _bars([100 + i for i in range(20)])
    outcomes = build_directional_outcomes(bars, future_bars=2, fast_period=3, slow_period=5)
    summary = summarize_directional_outcomes(outcomes)
    assert summary["decisions"] == len(outcomes)
    assert summary["long_decisions"] == len(outcomes)
    assert summary["short_decisions"] == 0
    assert summary["mean_net_return_bps"] > 0
