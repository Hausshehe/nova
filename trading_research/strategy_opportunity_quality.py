"""Evaluate market opportunities in a strategy-aware, cost-aware way."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

from .data import Bar
from .escalation import AdaptiveEscalator
from .market_monitor import MarketMonitor


@dataclass(frozen=True)
class StrategyOpportunityReport:
    opportunities: int
    actionable_opportunities: int
    recalls_with_ai_review: int
    actionable_recall: float
    transaction_cost_bps: float
    ignored_small_moves: int


def evaluate_strategy_opportunities(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    transaction_cost_bps_round_trip: float = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
) -> StrategyOpportunityReport:
    """Estimate actionable opportunities and whether escalation reviewed them.

    This remains diagnostic: it does not place trades or claim profitability.
    An opportunity must clear the transaction-cost buffer and have enough
    history for the SMA baseline. AI recall is measured from the same
    deterministic escalation policy used by the monitoring system.
    """
    if future_bars <= 0 or opportunity_move_bps <= 0:
        raise ValueError("future_bars and opportunity_move_bps must be positive")
    if transaction_cost_bps_round_trip < 0:
        raise ValueError("transaction_cost_bps_round_trip cannot be negative")
    if fast_period <= 0 or slow_period <= fast_period:
        raise ValueError("slow_period must exceed fast_period")
    if not bars:
        return StrategyOpportunityReport(0, 0, 0, 0.0, transaction_cost_bps_round_trip, 0)

    minimum_history = slow_period
    opportunities = actionable = ignored_small = 0
    actionable_indices: set[int] = set()

    for index, bar in enumerate(bars):
        future = bars[index + 1 : index + 1 + future_bars]
        if not future:
            continue
        move = max(abs(next_bar.close / bar.close - 1.0) * 10_000 for next_bar in future)
        if move < opportunity_move_bps:
            continue
        opportunities += 1
        if move < transaction_cost_bps_round_trip + opportunity_move_bps:
            ignored_small += 1
            continue
        if index + 1 < minimum_history:
            continue
        fast = sum(x.close for x in bars[index - fast_period + 1 : index + 1]) / fast_period
        slow = sum(x.close for x in bars[index - slow_period + 1 : index + 1]) / slow_period
        if fast != slow:
            actionable += 1
            actionable_indices.add(index)

    monitor = MarketMonitor()
    escalator = AdaptiveEscalator()
    events = monitor.observe_history("EURUSD", "D1", bars)
    timestamp_to_index = {bar.timestamp: index for index, bar in enumerate(bars)}
    reviewed_actionable: set[int] = set()

    for event in events:
        decision = escalator.evaluate(event)
        if not decision.request_ai:
            continue
        index = timestamp_to_index.get(event.timestamp)
        if index is not None and index in actionable_indices:
            reviewed_actionable.add(index)

    actionable_recall = (
        len(reviewed_actionable) / actionable if actionable else 0.0
    )
    return StrategyOpportunityReport(
        opportunities=opportunities,
        actionable_opportunities=actionable,
        recalls_with_ai_review=len(reviewed_actionable),
        actionable_recall=actionable_recall,
        transaction_cost_bps=transaction_cost_bps_round_trip,
        ignored_small_moves=ignored_small,
    )
