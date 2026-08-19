"""Causal strategy-aware hints for deciding when AI review is worthwhile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .data import Bar


@dataclass(frozen=True)
class StrategyEscalationHint:
    index: int
    request_ai: bool
    reason: str
    momentum_bps: float
    sma_gap_bps: float


def build_strategy_escalation_hints(
    bars: Sequence[Bar],
    *,
    fast_period: int = 20,
    slow_period: int = 50,
    momentum_bps: float = 8.0,
    max_sma_gap_bps: float = 35.0,
) -> tuple[StrategyEscalationHint, ...]:
    """Generate live-safe AI hints using only information available at each bar.

    This intentionally never looks into future bars. It identifies developing
    setups where momentum is present and the fast/slow SMA relationship is
    close enough that richer reasoning may be useful.
    """
    if fast_period <= 0 or slow_period <= fast_period:
        raise ValueError("slow_period must exceed fast_period")
    if momentum_bps <= 0 or max_sma_gap_bps <= 0:
        raise ValueError("thresholds must be positive")

    hints: list[StrategyEscalationHint] = []
    for index, bar in enumerate(bars):
        if index + 1 < slow_period:
            hints.append(StrategyEscalationHint(index, False, "insufficient history", 0.0, 0.0))
            continue

        fast = sum(x.close for x in bars[index - fast_period + 1 : index + 1]) / fast_period
        slow = sum(x.close for x in bars[index - slow_period + 1 : index + 1]) / slow_period
        gap_bps = abs(fast / slow - 1.0) * 10_000.0 if slow else 0.0

        previous_close = bars[index - 1].close if index else bar.close
        momentum = abs(bar.close / previous_close - 1.0) * 10_000.0 if previous_close else 0.0

        request = momentum >= momentum_bps and gap_bps <= max_sma_gap_bps
        reason = (
            "developing SMA setup with momentum"
            if request
            else "no developing setup"
        )
        hints.append(StrategyEscalationHint(index, request, reason, momentum, gap_bps))

    return tuple(hints)
