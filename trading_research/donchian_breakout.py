"""Frozen Donchian breakout trend-following hypothesis.

Rules are deliberately fixed before historical evaluation:
- look back 55 completed bars for an upside breakout;
- enter long when the current close is strictly above the prior 55-bar high;
- exit when the current close is strictly below the prior 20-bar low;
- execute state changes on the next bar open through the shared backtester.

No tuning, AI adjudication, or live execution belongs here.
"""

from __future__ import annotations

from typing import Sequence

from .contracts import Hypothesis
from .data import Bar

LOOKBACK_ENTRY = 55
LOOKBACK_EXIT = 20

HYPOTHESIS = Hypothesis(
    name="donchian_breakout_55_20_long_only",
    thesis="A sustained upside breakout above the prior 55 completed daily highs may carry forward through a trend until price breaks the prior 20 completed daily lows.",
    symbol="EURUSD",
    timeframe="1D",
    rules={
        "entry": "close > maximum high of previous 55 completed bars",
        "exit": "close < minimum low of previous 20 completed bars",
        "position": "long-only",
        "execution": "next-bar-open",
    },
    expected_edge="persistent directional movement after a multi-week breakout may exceed costs and simple directional baselines",
    falsifier="reject if any required evaluated segment fails the predefined research gates",
    rationale="Fixed breakout trend-following is structurally different from the rejected short-horizon momentum and mean-reversion hypotheses.",
)


def signal(bars: Sequence[Bar], index: int) -> bool:
    """Return desired long/flat state using only completed bars before ``index``."""
    if index < LOOKBACK_ENTRY:
        return False

    prior_entry = bars[index - LOOKBACK_ENTRY:index]
    entry_level = max(bar.high for bar in prior_entry)

    if index < LOOKBACK_EXIT:
        return False

    prior_exit = bars[index - LOOKBACK_EXIT:index]
    exit_level = min(bar.low for bar in prior_exit)

    previous_state = False
    if index > 0:
        previous_state = signal_state(bars, index - 1)

    if previous_state:
        return bars[index].close >= exit_level
    return bars[index].close > entry_level


def signal_state(bars: Sequence[Bar], index: int) -> bool:
    """Compute the position state recursively without mutating global state."""
    if index < LOOKBACK_ENTRY:
        return False

    prior_entry = bars[index - LOOKBACK_ENTRY:index]
    prior_exit = bars[max(0, index - LOOKBACK_EXIT):index]
    entry_level = max(bar.high for bar in prior_entry)
    exit_level = min(bar.low for bar in prior_exit)

    previous = signal_state(bars, index - 1) if index > 0 else False
    if previous:
        return bars[index].close >= exit_level
    return bars[index].close > entry_level
