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
    setup_score: float
    confidence_tier: str


def build_strategy_escalation_hints(
    bars: Sequence[Bar],
    *,
    fast_period: int = 20,
    slow_period: int = 50,
    momentum_bps: float = 5.0,
    max_sma_gap_bps: float = 50.0,
    slope_lookback: int = 3,
    slope_bps: float = 3.0,
    min_setup_score: float = 1.0,
    strong_setup_score: float = 1.5,
) -> tuple[StrategyEscalationHint, ...]:
    """Generate live-safe AI hints using only information available at each bar.

    Confidence tiers prevent weak signals from becoming automatic AI requests.
    Strong setups can escalate immediately; developing setups can escalate when
    the bounded market layer confirms meaningful change; weak setups stay local.
    """
    if fast_period <= 0 or slow_period <= fast_period:
        raise ValueError("slow_period must exceed fast_period")
    if momentum_bps <= 0 or max_sma_gap_bps <= 0 or slope_lookback <= 0 or slope_bps <= 0:
        raise ValueError("thresholds must be positive")
    if min_setup_score <= 0 or strong_setup_score < min_setup_score:
        raise ValueError("invalid setup score thresholds")

    hints: list[StrategyEscalationHint] = []
    for index, bar in enumerate(bars):
        if index + 1 < slow_period:
            hints.append(StrategyEscalationHint(index, False, "insufficient history", 0.0, 0.0, 0.0, "WEAK"))
            continue

        fast = sum(x.close for x in bars[index - fast_period + 1 : index + 1]) / fast_period
        slow = sum(x.close for x in bars[index - slow_period + 1 : index + 1]) / slow_period
        gap_bps = abs(fast / slow - 1.0) * 10_000.0 if slow else 0.0

        previous_close = bars[index - 1].close if index else bar.close
        momentum = abs(bar.close / previous_close - 1.0) * 10_000.0 if previous_close else 0.0

        slope_start = max(slow_period - 1, index - slope_lookback)
        fast_start = sum(x.close for x in bars[slope_start - fast_period + 1 : slope_start + 1]) / fast_period
        slow_start = sum(x.close for x in bars[slope_start - slow_period + 1 : slope_start + 1]) / slow_period
        gap_start = abs(fast_start / slow_start - 1.0) * 10_000.0 if slow_start else 0.0
        gap_slope = gap_bps - gap_start

        score = 0.0
        reasons: list[str] = []
        if momentum >= momentum_bps:
            score += 1.0
            reasons.append("fresh momentum")
        if abs(gap_slope) >= slope_bps:
            score += 1.0
            reasons.append("SMA gap changing")
        if gap_bps <= max_sma_gap_bps:
            score += 0.5
            reasons.append("SMA setup still developing")

        strong = score >= strong_setup_score and momentum >= momentum_bps
        developing = score >= min_setup_score and (momentum >= momentum_bps or abs(gap_slope) >= slope_bps)
        if strong:
            tier = "STRONG"
        elif developing:
            tier = "DEVELOPING"
        else:
            tier = "WEAK"

        request = strong or developing
        reason = "; ".join(reasons) if request else "no developing setup"
        hints.append(StrategyEscalationHint(index, request, reason, momentum, gap_bps, score, tier))

    return tuple(hints)
