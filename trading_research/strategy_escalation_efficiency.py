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
    bars: Sequence[Bar], *, future_bars: int, opportunity_move_bps: float,
    transaction_cost_bps_round_trip: float, fast_period: int, slow_period: int,
) -> set[int]:
    indices: set[int] = set()
    threshold = opportunity_move_bps + transaction_cost_bps_round_trip
    for index, bar in enumerate(bars):
        if index + 1 < slow_period:
            continue
        future = bars[index + 1:index + 1 + future_bars]
        if not future:
            continue
        move = max(abs(next_bar.close / bar.close - 1.0) * 10_000.0 for next_bar in future)
        if move < threshold:
            continue
        fast = sum(x.close for x in bars[index - fast_period + 1:index + 1]) / fast_period
        slow = sum(x.close for x in bars[index - slow_period + 1:index + 1]) / slow_period
        if fast != slow:
            indices.add(index)
    return indices


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
    """Measure selective strategy escalation without future leakage.

    One AI request is counted per bar/state, never once per emitted event.
    A candidate policy is accepted only when its walk-forward actionable recall
    reaches ``recall_floor``. If the adaptive filter falls below the floor, the
    system falls back to the previously proven broad causal bridge set.
    """
    if not bars:
        return StrategyEscalationEfficiencyReport(0, 0, 0, 0, 0.0, 0.0, 0)
    if not 0.0 < recall_floor <= 1.0:
        raise ValueError("recall_floor must be between 0 and 1")

    ordered = tuple(bars)
    monitor = MarketMonitor()
    events = monitor.observe_history("EURUSD", "15m", ordered)
    bridge_decisions = evaluate_strategy_escalation(
        ordered, events, fast_period=fast_period, slow_period=slow_period,
    )
    bridge_by_index = {}
    for decision in bridge_decisions:
        bridge_by_index.setdefault(decision.index, decision)

    actionable_indices = _actionable_indices(
        ordered,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
        transaction_cost_bps_round_trip=transaction_cost_bps_round_trip,
        fast_period=fast_period,
        slow_period=slow_period,
    )

    adaptive = build_walk_forward_policy(
        ordered,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
        transaction_cost_bps_round_trip=transaction_cost_bps_round_trip,
        fast_period=fast_period,
        slow_period=slow_period,
    )

    adaptive_indices = {
        decision.index for decision in adaptive if decision.request_ai
    }
    critical_indices = {
        index for index, decision in bridge_by_index.items()
        if decision.market_decision.level == "CRITICAL"
    }
    strong_indices = {
        index for index, decision in bridge_by_index.items()
        if getattr(decision.strategy_hint, "confidence_tier", "") == "STRONG"
    }
    adaptive_candidates = adaptive_indices | critical_indices | strong_indices
    adaptive_recall = (
        len(adaptive_candidates & actionable_indices) / len(actionable_indices)
        if actionable_indices else 1.0
    )

    broad_candidates = {
        index for index, decision in bridge_by_index.items() if decision.request_ai
    }
    if adaptive_recall >= recall_floor:
        selected_indices = adaptive_candidates
    else:
        selected_indices = broad_candidates

    # Exactly one AI decision per bar, even if multiple events were emitted.
    unique_ai = set(selected_indices)
    reviewed_actionable = actionable_indices & unique_ai
    actionable_recall = len(reviewed_actionable) / len(actionable_indices) if actionable_indices else 0.0

    justified_request_bars: set[int] = set()
    for index in unique_ai:
        future = ordered[index + 1:index + 1 + future_bars]
        if future:
            move = max(abs(next_bar.close / ordered[index].close - 1.0) * 10_000.0 for next_bar in future)
            if move >= opportunity_move_bps:
                justified_request_bars.add(index)

    opportunity_precision = len(justified_request_bars) / len(unique_ai) if unique_ai else 0.0
    quality = evaluate_strategy_opportunities(
        ordered,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
        transaction_cost_bps_round_trip=transaction_cost_bps_round_trip,
        fast_period=fast_period,
        slow_period=slow_period,
    )

    return StrategyEscalationEfficiencyReport(
        ai_requests=len(unique_ai),
        unique_ai_request_bars=len(unique_ai),
        actionable_opportunities=quality.actionable_opportunities,
        actionable_reviewed=len(reviewed_actionable),
        actionable_recall=actionable_recall,
        opportunity_precision=opportunity_precision,
        unnecessary_ai_requests=max(0, len(unique_ai) - len(justified_request_bars)),
    )
