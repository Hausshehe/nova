from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_research.broader_campaign_runner import (
    BOOTSTRAP_BLOCK,
    BOOTSTRAP_SAMPLES,
    breakout_volatility_signal_series,
    cross_market_signal_factory,
    mean_reversion_signal_series,
    momentum_signal_series,
    moving_block_bootstrap_ci,
)
from trading_research.data import Bar


def make_bars(closes: list[float]) -> list[Bar]:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(start + timedelta(hours=index), value, value + 1.0, value - 1.0, value, 1.0)
        for index, value in enumerate(closes)
    ]


def test_momentum_requires_50_bars_and_then_uses_frozen_sma_rule() -> None:
    bars = make_bars([100.0] * 50)
    states = momentum_signal_series(bars)
    assert states[:49] == [False] * 49
    assert states[49] is True


def test_mean_reversion_enters_on_frozen_two_sigma_rule_and_exits_at_mean() -> None:
    closes = [100.0] * 19 + [101.0, 70.0, 100.0]
    states = mean_reversion_signal_series(make_bars(closes))
    assert states[19] is False
    assert states[20] is True
    assert states[21] is False


def test_breakout_volatility_expansion_has_frozen_causal_entry() -> None:
    bars = make_bars([100.0] * 60)
    bars[59] = Bar(bars[59].timestamp, 101.0, 103.0, 99.0, 102.0, 1.0)
    states = breakout_volatility_signal_series(bars)
    assert states[58] is False
    assert states[59] is True


def test_cross_market_relative_behavior_uses_exact_common_timestamps() -> None:
    baseline = [100.0] * 20
    a = make_bars(baseline + [110.0, 111.0])
    b = make_bars(baseline + [100.0, 100.0])
    c = make_bars(baseline + [100.0, 100.0])
    signal = cross_market_signal_factory({"A": a, "B": b, "C": c}, "A")
    assert signal(a, 19) is False
    assert signal(a, 20) is True


def test_bootstrap_is_deterministic_and_uses_frozen_defaults() -> None:
    returns = [0.001, 0.002, -0.001, 0.003, -0.0005, 0.001]
    first = moving_block_bootstrap_ci(returns)
    second = moving_block_bootstrap_ci(returns)
    assert first == second
    assert BOOTSTRAP_BLOCK == 5
    assert BOOTSTRAP_SAMPLES == 1000
