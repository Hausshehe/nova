"""Measure strategy-aware escalation recall and AI-review efficiency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .adaptive_opportunity_policy import build_walk_forward_policy
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


def _actionable_indices(
    bars: Sequence[Bar],
    *,
    future_bars: int,
    opportunity_move_bps: float,
    transaction_cost_bps_round_trip: float,
    fast_period: int,
    slow_period: int,
) -> set[int]:
    threshold = opportunity_move_bps + transaction_cost_bps_round_trip
    result: set[int] = set()
    for index, bar in enumerate(bars):
        if index + 1 < slow_period:
            continue
        future = bars[index + 1 : index + 1 + future_bars]
        if not future:
            continue
        move = max(abs(next_bar.close / bar.close - 1.0) * 10_000.0 for next_bar in future)
        if move < threshold:
            continue
        fast = sum(x.close for x in bars[index - fast_period + 1 : index + 1]) / fast_period
        slow = sum(x.close for x in bars[index - slow_period + 1 : index + 1]) / slow_period
        if fast != slow:
            result.add(index)
    return result


def _precision(
    bars: Sequence[Bar],
    indices: set[int],
    *,
    future_bars: int,
    opportunity_move_bps: float,
) -> tuple[float, int]:
    justified: set[int] = set()
    for index in indices:
        future = bars[index + 1 : index + 1 + future_bars]
        if not future:
            continue
        move = max(abs(next_bar.close / bars[index].close - 1.0) * 10_000.0 for next_bar in future)
        if move >= opportunity_move_bps:
            justified.add(index)
    return (len(justified) / len(indices) if indices else 0.0, len(justified))


def evaluate_strategy_escalation_efficiency(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    transaction_cost_bps_round_trip: float = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
    recall_floor: float = 0.98,
) -> StrategyEscalationEfficiencyReport:
    """Optimize escalation only when the walk-forward policy preserves recall.

    The broad bridge policy is the safety baseline. The adaptive policy is an
    optimization candidate, never the authority: if its walk-forward recall
    falls below ``recall_floor``, the evaluator automatically uses the broad
    baseline. This prevents an efficiency optimization from silently trading
    away opportunity recall.
    """
    if not 0 < recall_floor <= 1:
        raise ValueError("recall_floor must be between 0 and 1")
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

    # One AI decision per bar. The broad bridge policy is the known-safe
    # baseline that the optimizer is never allowed to undercut.
    baseline_indices = {decision.index for decision in decisions if decision.request_ai}
    adaptive = build_walk_forward_policy(
        ordered,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
        transaction_cost_bps_round_trip=transaction_cost_bps_round_trip,
        fast_period=fast_period,
        slow_period=slow_period,
    )
    adaptive_indices = {decision.index for decision in adaptive if decision.request_ai}

    actionable = _actionable_indices(
        ordered,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
        transaction_cost_bps_round_trip=transaction_cost_bps_round_trip,
        fast_period=fast_period,
        slow_period=slow_period,
    )
    adaptive_recall = len(actionable & adaptive_indices) / len(actionable) if actionable else 0.0
    selected = adaptive_indices if adaptive_recall >= recall_floor else baseline_indices

    reviewed = actionable & selected
    recall = len(reviewed) / len(actionable) if actionable else 0.0
    precision, justified_count = _precision(
        ordered,
        selected,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
    )

    quality = evaluate_strategy_opportunities(
        ordered,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
        transaction_cost_bps_round_trip=transaction_cost_bps_round_trip,
        fast_period=fast_period,
        slow_period=slow_period,
    )

    return StrategyEscalationEfficiencyReport(
        ai_requests=len(selected),
        unique_ai_request_bars=len(selected),
        actionable_opportunities=quality.actionable_opportunities,
        actionable_reviewed=len(reviewed),
        actionable_recall=recall,
        opportunity_precision=precision,
        unnecessary_ai_requests=max(0, len(selected) - justified_count),
    )
