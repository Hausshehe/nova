"""Bridge strategy-aware live hints into the bounded escalation layer."""

from __future__ import annotations

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
) -> tuple[StrategyEscalationDecision, ...]:
    """Combine causal strategy hints with state-aware market escalation."""
    hints = build_strategy_escalation_hints(
        bars,
        fast_period=fast_period,
        slow_period=slow_period,
        momentum_bps=momentum_bps,
        max_sma_gap_bps=max_sma_gap_bps,
        slope_lookback=slope_lookback,
        slope_bps=slope_bps,
        min_setup_score=min_setup_score,
    )
    by_timestamp = {bar.timestamp: i for i, bar in enumerate(bars)}

    escalator = AdaptiveEscalator(thresholds)
    results: list[StrategyEscalationDecision] = []
    for event in events:
        index = by_timestamp.get(event.timestamp)
        if index is None:
            continue
        hint = hints[index]
        market_state = hint.sma_gap_bps + hint.momentum_bps
        market_decision = escalator.evaluate(event, state_value_bps=market_state)
        request = market_decision.request_ai
        reason = market_decision.reason

        if hint.request_ai and not request:
            configured = thresholds or EscalationThresholds()
            synthetic = MarketEvent(
                event_type="PRICE_MOVE",
                timestamp=event.timestamp,
                symbol=event.symbol,
                timeframe=event.timeframe,
                reason=f"strategy hint: {hint.reason}",
                price=event.price,
                change_bps=configured.elevated_move_bps,
                spread_bps=event.spread_bps,
            )
            promoted = escalator.evaluate(synthetic, state_value_bps=market_state)
            request = promoted.request_ai
            reason = (
                f"strategy hint: {hint.reason}"
                if request
                else "strategy hint suppressed by state-aware AI cooldown"
            )
        elif hint.request_ai and request:
            reason = f"strategy hint: {hint.reason}"

        results.append(StrategyEscalationDecision(index, request, reason, hint, market_decision))
    return tuple(results)
