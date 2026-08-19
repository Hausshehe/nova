"""Frozen weekday-effect hypothesis for EURUSD daily research.

Rules are fixed before historical evaluation:
- if Friday closes above the prior completed trading day's close, request a long;
- the shared backtester executes that request at the next trading day's open;
- the position is held for exactly one subsequent trading day and then exited
  at the following trading day's open.

No thresholds, parameter search, AI, or adaptive selection are involved.
"""

from __future__ import annotations

from typing import Sequence

from .contracts import Hypothesis
from .data import Bar

HYPOTHESIS = Hypothesis(
    name="friday_followthrough_next_session_long_only",
    thesis="A positive Friday close-to-close move may continue into the next trading session because of weekly positioning and liquidity effects.",
    symbol="EURUSD",
    timeframe="1D",
    rules={
        "signal": "on Friday, close > prior completed trading-day close",
        "position": "long-only",
        "hold": "next trading day only",
        "execution": "next-bar-open",
    },
    expected_edge="weekly positioning and weekend risk management may produce a small repeatable Monday/next-session continuation after positive Fridays",
    falsifier="reject if any required evaluated segment fails the predefined research gates",
    rationale="Calendar/weekday behavior is structurally different from horizon selection, mean reversion, and breakout trend following.",
)


class FridayContinuationSignal:
    """Sequential long/flat state for one-day post-Friday continuation."""

    def __init__(self) -> None:
        self._bars_id: int | None = None
        self._last_index = -1
        self._in_position = False
        self._exit_index: int | None = None

    def _reset_if_new_sequence(self, bars: Sequence[Bar], index: int) -> None:
        if self._bars_id != id(bars) or index == 0:
            self._bars_id = id(bars)
            self._last_index = -1
            self._in_position = False
            self._exit_index = None

    def __call__(self, bars: Sequence[Bar], index: int) -> bool:
        self._reset_if_new_sequence(bars, index)
        if index < self._last_index:
            raise ValueError("FridayContinuationSignal must be evaluated chronologically")
        if index == self._last_index:
            return self._in_position

        for current in range(self._last_index + 1, index + 1):
            if self._in_position and self._exit_index is not None and current >= self._exit_index:
                self._in_position = False
                self._exit_index = None

            if current > 0 and bars[current].timestamp.weekday() == 4:
                positive_friday = bars[current].close > bars[current - 1].close
                if positive_friday:
                    self._in_position = True
                    self._exit_index = current + 1

        self._last_index = index
        return self._in_position


signal = FridayContinuationSignal()
