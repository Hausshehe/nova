"""Bridge strategy-aware live hints into the bounded escalation layer."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Sequence

from .data import Bar
from .escalation import AdaptiveEscalator, EscalationDecision, EscalationThresholds
from .market_monitor import MarketEvent
from .strategy_escalation import StrategyEscalationHint, build_strategy_escalation_hints


@dataclass(frozen=True)
class StrategyEscalationDecision:
    index: int
    request_ai: bool
    reason: str
    strategy_hint: StrategyEscalationHint
    market_decision: EscalationDecision


def evaluate_strategy_escalation(
    bars: Sequence[Bar],
    events: Sequence[MarketEvent],
    *,
    thresholds: EscalationThresholds | None = None,
    fast_period: int = 20,
    slow_period: int = 50,
    momentum_bps: float = 5.0,
    max_sma_gap_bps: float = 50.0,
    slope_lookback: int = 3,
    slope_bps: float = 3.0,
    min_setup_score: float = 1.0,
    strong_setup_score: float = 1.5,
) -> tuple[StrategyEscalationDecision, ...]:
    """Combine confidence-tiered strategy hints with bounded market escalation.

    An event is evaluated against the latest bar whose timestamp is not later
    than the event. This avoids dropping live events merely because they occur
    between bar timestamps while never introducing a future bar into context.
    """
    if not bars:
        return ()

    hints = build_strategy_escalation_hints(
        bars,
        fast_period=fast_period,
        slow_period=slow_period,
        momentum_bps=momentum_bps,
        max_sma_gap_bps=max_sma_gap_bps,
        slope_lookback=slope_lookback,
        slope_bps=slope_bps,
        min_setup_score=min_setup_score,
        strong_setup_score=strong_setup_score,
    )
    timestamps = [bar.timestamp for bar in bars]
    escalator = AdaptiveEscalator(thresholds)
    results: list[StrategyEscalationDecision] = []

    for event in events:
        index = bisect_right(timestamps, event.timestamp) - 1
        if index < 0:
            continue
        hint = hints[index]
        state_value = hint.sma_gap_bps + hint.momentum_bps
        market_decision = escalator.evaluate(event, state_value_bps=state_value)

        if hint.confidence_tier == "STRONG":
            if market_decision.request_ai:
                request = True
                reason = f"strong strategy hint: {hint.reason}"
            else:
                configured = thresholds or EscalationThresholds()
                synthetic = MarketEvent(
                    event_type="PRICE_MOVE",
                    timestamp=event.timestamp,
                    symbol=event.symbol,
                    timeframe=event.timeframe,
                    reason=f"strong strategy hint: {hint.reason}",
                    price=event.price,
                    change_bps=configured.elevated_move_bps,
                    spread_bps=event.spread_bps,
                )
                promoted = escalator.evaluate(synthetic, state_value_bps=state_value)
                request = promoted.request_ai
                reason = "strong strategy hint confirmed" if request else "strong strategy hint suppressed by AI cooldown"
        elif hint.confidence_tier == "DEVELOPING":
            request = market_decision.request_ai
            reason = (
                f"developing strategy confirmed by market escalation: {hint.reason}"
                if request
                else market_decision.reason
            )
        else:
            request = market_decision.request_ai
            reason = market_decision.reason

        results.append(StrategyEscalationDecision(index, request, reason, hint, market_decision))

    return tuple(results)
