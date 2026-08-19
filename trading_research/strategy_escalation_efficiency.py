"""Measure strategy-aware escalation recall and AI-review efficiency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .data import Bar
from .market_monitor import MarketMonitor
from .strategy_escalation_bridge import evaluate_strategy_escalation
from .strategy_opportunity_quality import evaluate_strategy_opportunities


@dataclass(frozen=True)
class StrategyEscalationEfficiencyReport:
    ai_requests: int
    unique_ai_request_bars: int
    actionable_opportunities: int
    actionable_reviewed: int
    actionable_recall: float
    opportunity_precision: float
    unnecessary_ai_requests: int


def evaluate_strategy_escalation_efficiency(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    transaction_cost_bps_round_trip: float = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
) -> StrategyEscalationEfficiencyReport:
    """Measure whether strategy-aware AI requests are useful without future leakage."""
    if not bars:
        return StrategyEscalationEfficiencyReport(0, 0, 0, 0, 0.0, 0.0, 0)

    ordered = tuple(bars)
    monitor = MarketMonitor()
    events = monitor.observe_history("EURUSD", "15m", ordered)
    decisions = evaluate_strategy_escalation(
        ordered,
        events,
        fast_period=fast_period,
        slow_period=slow_period,
    )

    ai_indices = [decision.index for decision in decisions if decision.request_ai]
    unique_ai = set(ai_indices)

    quality = evaluate_strategy_opportunities(
        ordered,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
        transaction_cost_bps_round_trip=transaction_cost_bps_round_trip,
        fast_period=fast_period,
        slow_period=slow_period,
    )

    actionable_indices: set[int] = set()
    for index, bar in enumerate(ordered):
        future = ordered[index + 1 : index + 1 + future_bars]
        if len(future) == 0 or index + 1 < slow_period:
            continue
        move = max(abs(next_bar.close / bar.close - 1.0) * 10_000.0 for next_bar in future)
        if move < opportunity_move_bps + transaction_cost_bps_round_trip:
            continue
        fast = sum(x.close for x in ordered[index - fast_period + 1 : index + 1]) / fast_period
        slow = sum(x.close for x in ordered[index - slow_period + 1 : index + 1]) / slow_period
        if fast != slow:
            actionable_indices.add(index)

    reviewed_actionable = actionable_indices & unique_ai
    actionable_recall = len(reviewed_actionable) / len(actionable_indices) if actionable_indices else 0.0

    justified_request_bars: set[int] = set()
    for index in unique_ai:
        future = ordered[index + 1 : index + 1 + future_bars]
        if not future:
            continue
        move = max(abs(next_bar.close / ordered[index].close - 1.0) * 10_000.0 for next_bar in future)
        if move >= opportunity_move_bps:
            justified_request_bars.add(index)

    opportunity_precision = len(justified_request_bars) / len(unique_ai) if unique_ai else 0.0
    return StrategyEscalationEfficiencyReport(
        ai_requests=len(ai_indices),
        unique_ai_request_bars=len(unique_ai),
        actionable_opportunities=quality.actionable_opportunities,
        actionable_reviewed=len(reviewed_actionable),
        actionable_recall=actionable_recall,
        opportunity_precision=opportunity_precision,
        unnecessary_ai_requests=max(0, len(unique_ai) - len(justified_request_bars)),
    )
