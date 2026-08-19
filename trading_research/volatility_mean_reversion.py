"""Frozen volatility-normalized mean-reversion research hypothesis.

This module contains one deliberately fixed hypothesis. It is not an adaptive
optimizer and it does not tune parameters against historical results.

Rule:
- use the last 20 completed closes at decision time;
- compute the rolling mean and population standard deviation;
- when flat, enter long when the current close is at or below mean - 2 * std;
- while long, remain long until the current close reaches or exceeds the mean;
- execute state changes at the next bar open.
"""

from __future__ import annotations

from typing import Sequence

from .contracts import Hypothesis
from .data import Bar

LOOKBACK = 20
Z_ENTRY = 2.0

HYPOTHESIS = Hypothesis(
    name="volatility_normalized_mean_reversion_20_2z",
    thesis="Large negative deviations from a 20-bar mean, normalized by recent volatility, tend to revert toward the mean.",
    symbol="EURUSD",
    timeframe="D1",
    rules={
        "lookback": str(LOOKBACK),
        "entry_z": str(Z_ENTRY),
        "exit": "close >= rolling_mean",
        "position": "long_flat",
        "execution": "next_bar_open",
    },
    expected_edge="After costs, negative 20-bar z-score extremes should have positive subsequent long-only expectancy before mean reversion.",
    falsifier="Reject if the predefined train/validation/test evidence fails the research gates or if independent validation does not reproduce the effect.",
    rationale="A structurally different hypothesis from horizon selection, expert consensus, and online horizon adaptation.",
)


def _stats(bars: Sequence[Bar], index: int) -> tuple[float, float] | None:
    if index < LOOKBACK - 1:
        return None
    closes = [bars[pos].close for pos in range(index - LOOKBACK + 1, index + 1)]
    mean = sum(closes) / LOOKBACK
    variance = sum((value - mean) ** 2 for value in closes) / LOOKBACK
    return mean, variance ** 0.5


def desired_long_state(bars: Sequence[Bar], index: int) -> bool:
    """Compute desired position at ``index`` using bars through ``index`` only.

    State is recomputed from the start so the signal remains pure and
    deterministic for the stateless backtest interface.
    """
    if index < LOOKBACK - 1:
        return False

    in_position = False
    for current in range(LOOKBACK - 1, index + 1):
        stats = _stats(bars, current)
        if stats is None:
            continue
        mean, std = stats
        close = bars[current].close
        if not in_position:
            if std > 0.0 and close <= mean - Z_ENTRY * std:
                in_position = True
        elif close >= mean:
            in_position = False
    return in_position


def signal(bars: Sequence[Bar], index: int) -> bool:
    """Return desired long/flat state using information available by ``index`` only."""
    return desired_long_state(bars, index)


def exit_condition(bars: Sequence[Bar], index: int) -> bool:
    """Return whether the predefined mean-reversion exit is reached."""
    if index < LOOKBACK - 1 or not desired_long_state(bars, index):
        return False
    stats = _stats(bars, index)
    if stats is None:
        return False
    mean, _ = stats
    return bars[index].close >= mean
