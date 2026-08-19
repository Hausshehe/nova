"""Bounded evaluation of Nova AI decisions against causal outcome labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .data import Bar
from .decision_contract import AIRecommendation
from .high_recall_candidate_policy import high_recall_candidate_indices
from .market_monitor import MarketMonitor
from .market_reasoner import GroqMarketReasoner, MarketAnalysis
from .outcome_ledger import build_outcome_ledger


@dataclass(frozen=True)
class AIDecisionOutcomeRecord:
    index: int
    assessment: str
    urgency: str
    action: str
    confidence: float
    actionable_label: bool
    max_abs_move_bps: float
    max_up_move_bps: float
    max_down_move_bps: float


@dataclass(frozen=True)
class AIDecisionOutcomeReport:
    policy: str
    sampled_candidate_bars: int
    evaluated_ai_decisions: int
    api_errors: int
    actionable_opportunities: int
    actionable_decisions: int
    actionable_recall: float
    decision_precision: float
    mean_confidence_actionable: float
    mean_confidence_not_actionable: float


def _recommendation_action(analysis: MarketAnalysis) -> str:
    recommendation: AIRecommendation | None = analysis.recommendation
    return recommendation.action if recommendation is not None else analysis.assessment


def _stratified_candidate_sample(candidate_indices: Sequence[int], ledger, limit: int) -> list[int]:
    """Choose a deterministic mix of actionable/non-actionable candidates.

    Future outcome labels are used here only to construct an evaluation sample;
    they never participate in the candidate gate or the AI decision itself.
    """
    if limit <= 0:
        return []
    eligible = [index for index in candidate_indices if ledger[index].actionable_label is not None]
    actionable = [index for index in eligible if ledger[index].actionable_label]
    non_actionable = [index for index in eligible if not ledger[index].actionable_label]

    actionable_quota = min((limit + 1) // 2, len(actionable))
    non_actionable_quota = min(limit - actionable_quota, len(non_actionable))

    # If one class is scarce, fill the remaining slots from the other class.
    remaining = limit - actionable_quota - non_actionable_quota
    if remaining:
        extra_actionable = min(remaining, len(actionable) - actionable_quota)
        actionable_quota += extra_actionable
        remaining -= extra_actionable
    if remaining:
        non_actionable_quota += min(remaining, len(non_actionable) - non_actionable_quota)

    selected = actionable[:actionable_quota] + non_actionable[:non_actionable_quota]
    return sorted(selected)


def evaluate_ai_decision_outcomes(
    bars: Sequence[Bar],
    *,
    reasoner: GroqMarketReasoner,
    sample_limit: int = 32,
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    transaction_cost_bps: float = 4.0,
    strategy_context_builder: Callable[[int], str] | None = None,
) -> AIDecisionOutcomeReport:
    """Evaluate a bounded, stratified sample without changing the candidate gate."""
    if sample_limit <= 0:
        raise ValueError("sample_limit must be positive")

    candidate_indices = sorted(high_recall_candidate_indices(bars))
    if not candidate_indices:
        return AIDecisionOutcomeReport(
            "high_recall_candidate_ai_outcome_evaluation", 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0
        )

    ledger = build_outcome_ledger(
        bars,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
        transaction_cost_bps_round_trip=transaction_cost_bps,
    )
    candidate_indices = _stratified_candidate_sample(candidate_indices, ledger, sample_limit)
    if not candidate_indices:
        return AIDecisionOutcomeReport(
            "high_recall_candidate_ai_outcome_evaluation", 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0
        )

    events = MarketMonitor().observe_history("EURUSD", "15m", bars)
    event_by_timestamp = {event.timestamp: event for event in events}

    evaluated: list[AIDecisionOutcomeRecord] = []
    errors = 0
    for index in candidate_indices:
        bar = bars[index]
        event = event_by_timestamp.get(bar.timestamp)
        if event is None:
            errors += 1
            continue
        try:
            analysis = reasoner.analyze(
                event,
                strategy_context=strategy_context_builder(index) if strategy_context_builder else "",
            )
        except Exception:
            errors += 1
            continue
        outcome = ledger[index]
        evaluated.append(
            AIDecisionOutcomeRecord(
                index=index,
                assessment=analysis.assessment,
                urgency=analysis.urgency,
                action=_recommendation_action(analysis),
                confidence=analysis.recommendation.confidence if analysis.recommendation else 0.0,
                actionable_label=outcome.actionable_label,
                max_abs_move_bps=outcome.max_abs_close_move_bps or 0.0,
                max_up_move_bps=outcome.max_up_close_move_bps or 0.0,
                max_down_move_bps=outcome.max_down_close_move_bps or 0.0,
            )
        )

    actionable = [row for row in evaluated if row.actionable_label]
    decisions_marked_actionable = [row for row in evaluated if row.action in {"ENTER", "EXIT", "SETUP", "RISK"}]
    actionable_decisions = [row for row in actionable if row.action in {"ENTER", "EXIT", "SETUP", "RISK"}]
    decision_precision = (
        len([row for row in decisions_marked_actionable if row.actionable_label]) / len(decisions_marked_actionable)
        if decisions_marked_actionable
        else 0.0
    )
    mean_confidence_actionable = sum(row.confidence for row in actionable) / len(actionable) if actionable else 0.0
    not_actionable = [row for row in evaluated if not row.actionable_label]
    mean_confidence_not_actionable = (
        sum(row.confidence for row in not_actionable) / len(not_actionable) if not_actionable else 0.0
    )

    return AIDecisionOutcomeReport(
        policy="high_recall_candidate_ai_outcome_evaluation",
        sampled_candidate_bars=len(candidate_indices),
        evaluated_ai_decisions=len(evaluated),
        api_errors=errors,
        actionable_opportunities=len(actionable),
        actionable_decisions=len(actionable_decisions),
        actionable_recall=(len(actionable_decisions) / len(actionable) if actionable else 0.0),
        decision_precision=decision_precision,
        mean_confidence_actionable=mean_confidence_actionable,
        mean_confidence_not_actionable=mean_confidence_not_actionable,
    )
