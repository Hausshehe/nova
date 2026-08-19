"""Frozen Donchian breakout trend-following hypothesis.

Rules are deliberately fixed before historical evaluation:
- look back 55 completed bars for an upside breakout;
- enter long when the current close is strictly above the prior 55-bar high;
- exit when the current close is strictly below the prior 20-bar low;
- execute state changes on the next bar open through the shared backtester.

The signal is sequential because the shared backtester evaluates indices in
chronological order. A new bar sequence resets its state, keeping train,
validation, and test segments isolated.
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


class DonchianSignal:
    """Sequential long/flat state machine used by the chronological backtester."""

    def __init__(self) -> None:
        self._bars_id: int | None = None
        self._last_index = -1
        self._in_position = False

    def _reset_if_new_sequence(self, bars: Sequence[Bar], index: int) -> None:
        if self._bars_id != id(bars) or index == 0:
            self._bars_id = id(bars)
            self._last_index = -1
            self._in_position = False

    def __call__(self, bars: Sequence[Bar], index: int) -> bool:
        self._reset_if_new_sequence(bars, index)
        if index < self._last_index:
            raise ValueError("DonchianSignal must be evaluated chronologically")
        if index == self._last_index:
            return self._in_position

        for current in range(self._last_index + 1, index + 1):
            if current < LOOKBACK_ENTRY:
                self._in_position = False
                continue

            prior_entry = bars[current - LOOKBACK_ENTRY:current]
            entry_level = max(bar.high for bar in prior_entry)

            prior_exit = bars[current - LOOKBACK_EXIT:current]
            exit_level = min(bar.low for bar in prior_exit)

            if self._in_position:
                if bars[current].close < exit_level:
                    self._in_position = False
            elif bars[current].close > entry_level:
                self._in_position = True

        self._last_index = index
        return self._in_position


signal = DonchianSignal()
