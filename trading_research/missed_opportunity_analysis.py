"""Classify missed strategy opportunities by foreseeable escalation cause."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .data import Bar
from .market_monitor import MarketMonitor
from .strategy_escalation_bridge import evaluate_strategy_escalation


@dataclass(frozen=True)
class MissedOpportunityAnalysis:
    actionable_opportunities: int
    reviewed_actionable: int
    missed_actionable: int
    causes: dict[str, int]


def analyze_missed_opportunities(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    transaction_cost_bps_round_trip: float = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
) -> MissedOpportunityAnalysis:
    """Classify actionable opportunities that received no AI review.

    The future window is used only to label the opportunity after replay; all
    escalation features are computed causally from bars available at that bar.
    """
    if not bars:
        return MissedOpportunityAnalysis(0, 0, 0, {})
    actionable: set[int] = set()
    for index, bar in enumerate(bars):
        future = bars[index + 1 : index + 1 + future_bars]
        if not future:
            continue
        move = max(abs(next_bar.close / bar.close - 1.0) * 10_000 for next_bar in future)
        if move < opportunity_move_bps:
            continue
        if move < opportunity_move_bps + transaction_cost_bps_round_trip:
            continue
        if index + 1 < slow_period:
            continue
        fast = sum(x.close for x in bars[index - fast_period + 1 : index + 1]) / fast_period
        slow = sum(x.close for x in bars[index - slow_period + 1 : index + 1]) / slow_period
        if fast != slow:
            actionable.add(index)

    events = MarketMonitor().observe_history("EURUSD", "D1", bars)
    decisions = evaluate_strategy_escalation(
        bars,
        events,
        fast_period=fast_period,
        slow_period=slow_period,
    )
    reviewed = {decision.index for decision in decisions if decision.request_ai}
    missed = actionable - reviewed

    causes: dict[str, int] = {}
    for index in sorted(missed):
        hint = decisions[index].strategy_hint if index < len(decisions) else None
        if hint is None:
            cause = "no_market_event_at_bar"
        elif hint.request_ai:
            cause = "cooldown_or_duplicate_event_suppression"
        elif hint.reason == "insufficient history":
            cause = "insufficient_history"
        else:
            cause = "strategy_hint_not_triggered"
        causes[cause] = causes.get(cause, 0) + 1

    return MissedOpportunityAnalysis(
        actionable_opportunities=len(actionable),
        reviewed_actionable=len(actionable & reviewed),
        missed_actionable=len(missed),
        causes=causes,
    )
