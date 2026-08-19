"""Bridge strategy-aware live hints into the bounded escalation layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .data import Bar
from .escalation import EscalationDecision, EscalationThresholds
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
    momentum_bps: float = 8.0,
    max_sma_gap_bps: float = 35.0,
) -> tuple[StrategyEscalationDecision, ...]:
    """Combine causal strategy hints with normal market escalation.

    A strategy hint can promote an otherwise routine observation, but it is
    still subject to the same per-symbol/timeframe AI cooldown as ordinary
    escalation. This prevents strategy awareness from turning into an
    unrestricted AI polling loop.
    """
    hints = build_strategy_escalation_hints(
        bars,
        fast_period=fast_period,
        slow_period=slow_period,
        momentum_bps=momentum_bps,
        max_sma_gap_bps=max_sma_gap_bps,
    )
    by_timestamp = {bar.timestamp: i for i, bar in enumerate(bars)}

    # Import here to keep the bridge's dependency surface explicit.
    from .escalation import AdaptiveEscalator

    escalator = AdaptiveEscalator(thresholds)
    results: list[StrategyEscalationDecision] = []
    for event in events:
        index = by_timestamp.get(event.timestamp)
        if index is None:
            continue
        market_decision = escalator.evaluate(event)
        hint = hints[index]
        request = market_decision.request_ai or hint.request_ai
        if request and not market_decision.request_ai and hint.request_ai:
            # A strategy promotion must respect the same cooldown. Re-evaluate
            # through a synthetic meaningful event so the escalator owns the
            # cooldown state instead of duplicating it here.
            synthetic = MarketEvent(
                event_type="PRICE_MOVE",
                timestamp=event.timestamp,
                symbol=event.symbol,
                timeframe=event.timeframe,
                change_bps=max(momentum_bps, 0.0),
                spread_bps=event.spread_bps,
            )
            promoted = escalator.evaluate(synthetic)
            request = promoted.request_ai
            if request:
                reason = f"strategy hint: {hint.reason}"
            else:
                reason = f"strategy hint suppressed by AI cooldown"
        else:
            reason = market_decision.reason
        results.append(StrategyEscalationDecision(index, request, reason, hint, market_decision))
    return tuple(results)
