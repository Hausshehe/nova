"""Frozen opening-gap continuation hypothesis for EURUSD daily research.

Rules are fixed before historical evaluation:
- if the current day's open is above the prior completed day's close, request a long;
- the shared backtester executes that request at the next trading day's open;
- the position is held for exactly one subsequent trading day and then exits.

The hypothesis uses the opening discontinuity itself rather than close-to-close
momentum, calendar effects, mean-reversion thresholds, or breakout levels.
No threshold, parameter search, AI, or adaptive selection is involved.
"""

from __future__ import annotations

from typing import Sequence

from .contracts import Hypothesis
from .data import Bar

HYPOTHESIS = Hypothesis(
    name="positive_opening_gap_next_session_long_only",
    thesis="A positive daily opening gap above the prior completed close may contain short-horizon directional information that persists into the following trading session.",
    symbol="EURUSD",
    timeframe="1D",
    rules={
        "signal": "when current open > prior completed day's close",
        "position": "long-only",
        "hold": "next trading day only",
        "execution": "next-bar-open",
    },
    expected_edge="overnight repricing and order-flow imbalance may leave short-lived continuation after a positive opening discontinuity",
    falsifier="reject if any required evaluated segment fails the predefined research gates",
    rationale="Opening-gap information is structurally distinct from the tested close-to-close horizon/expert, rolling mean-reversion, Donchian breakout, and Friday calendar families.",
)


class GapContinuationSignal:
    """Sequential long/flat state for one-day post-gap continuation."""

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
            raise ValueError("GapContinuationSignal must be evaluated chronologically")
        if index == self._last_index:
            return self._in_position

        for current in range(self._last_index + 1, index + 1):
            just_exited = False
            if self._in_position and self._exit_index is not None and current >= self._exit_index:
                self._in_position = False
                self._exit_index = None
                just_exited = True

            if (
                not just_exited
                and current > 0
                and not self._in_position
                and bars[current].open > bars[current - 1].close
            ):
                self._in_position = True
                self._exit_index = current + 1

        self._last_index = index
        return self._in_position


signal = GapContinuationSignal()
