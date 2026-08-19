"""Frozen volatility-normalized mean-reversion research hypothesis.

This module contains one deliberately fixed hypothesis. It is not an adaptive
optimizer and it does not tune its parameters against historical results.

Rule:
- use the last 20 completed closes at decision time;
- compute the rolling mean and population standard deviation;
- enter long when the current close is at or below mean - 2 * std;
- remain long while below the mean;
- exit when the current close reaches or exceeds the rolling mean.

The backtester executes any state change at the next bar open, preserving
causality.
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


def signal(bars: Sequence[Bar], index: int) -> bool:
    """Return desired long/flat state using information available by ``index`` only."""
    if index < LOOKBACK - 1:
        return False

    closes = [bars[pos].close for pos in range(index - LOOKBACK + 1, index + 1)]
    mean = sum(closes) / LOOKBACK
    variance = sum((value - mean) ** 2 for value in closes) / LOOKBACK
    std = variance ** 0.5

    if std == 0.0:
        return False

    threshold = mean - Z_ENTRY * std
    return bars[index].close <= threshold


def exit_condition(bars: Sequence[Bar], index: int) -> bool:
    """Return whether the predefined mean-reversion exit is reached."""
    if index < LOOKBACK - 1:
        return False

    closes = [bars[pos].close for pos in range(index - LOOKBACK + 1, index + 1)]
    mean = sum(closes) / LOOKBACK
    return bars[index].close >= mean
