"""Deterministic outcome-quality analysis for the trusted high-recall candidate set."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .outcome_ledger import OutcomeRecord, build_outcome_ledger


@dataclass(frozen=True)
class CandidateOutcomeMetrics:
    candidate_bars: int
    complete_candidate_bars: int
    actionable_candidates: int
    actionable_rate: float
    opportunity_bars: int
    opportunity_recall: float
    mean_max_abs_move_bps: float
    median_max_abs_move_bps: float
    mean_net_max_abs_move_bps: float
    mean_max_up_move_bps: float
    mean_max_down_move_bps: float


def _metrics(records: Sequence[OutcomeRecord], indices: set[int], actionable_set: set[int], opportunity_set: set[int]) -> CandidateOutcomeMetrics:
    complete = [r for r in records if r.index in indices and not r.insufficient_future_window]
    actionable = [r for r in complete if r.actionable_label]
    opportunities = [r for r in complete if r.opportunity_label]
    abs_moves = [r.max_abs_close_move_bps for r in complete if r.max_abs_close_move_bps is not None]
    net_moves = [r.net_max_abs_move_bps for r in complete if r.net_max_abs_move_bps is not None]
    up_moves = [r.max_up_close_move_bps for r in complete if r.max_up_close_move_bps is not None]
    down_moves = [r.max_down_close_move_bps for r in complete if r.max_down_close_move_bps is not None]
    return CandidateOutcomeMetrics(
        candidate_bars=len(indices),
        complete_candidate_bars=len(complete),
        actionable_candidates=len(actionable),
        actionable_rate=len(actionable) / len(complete) if complete else 0.0,
        opportunity_bars=len(opportunities),
        opportunity_recall=len(actionable) / len(actionable_set) if actionable_set else 0.0,
        mean_max_abs_move_bps=mean(abs_moves) if abs_moves else 0.0,
        median_max_abs_move_bps=median(abs_moves) if abs_moves else 0.0,
        mean_net_max_abs_move_bps=mean(net_moves) if net_moves else 0.0,
        mean_max_up_move_bps=mean(up_moves) if up_moves else 0.0,
        mean_max_down_move_bps=mean(down_moves) if down_moves else 0.0,
    )


def evaluate_candidate_outcome_quality(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    transaction_cost_bps: float = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
    folds: int = 4,
) -> tuple[CandidateOutcomeMetrics, tuple[tuple[int, CandidateOutcomeMetrics], ...]]:
    """Evaluate outcomes for the trusted high-recall candidate set only."""
    if folds <= 0:
        raise ValueError("folds must be positive")
    records = build_outcome_ledger(
        bars,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
        transaction_cost_bps_round_trip=transaction_cost_bps,
        fast_period=fast_period,
        slow_period=slow_period,
    )
    candidates = high_recall_candidate_indices(
        bars,
        fast_period=fast_period,
        slow_period=slow_period,
    )
    complete = [r for r in records if not r.insufficient_future_window]
    actionable_set = {r.index for r in complete if r.actionable_label}
    opportunity_set = {r.index for r in complete if r.opportunity_label}
    full = _metrics(records, candidates, actionable_set, opportunity_set)

    n = len(bars)
    fold_size = n // folds
    fold_metrics: list[tuple[int, CandidateOutcomeMetrics]] = []
    for fold in range(folds):
        start = fold * fold_size
        end = n if fold == folds - 1 else (fold + 1) * fold_size
        fold_candidates = {i for i in candidates if start <= i < end}
        fold_actionable = {i for i in actionable_set if start <= i < end}
        fold_opportunities = {i for i in opportunity_set if start <= i < end}
        fold_metrics.append((fold + 1, _metrics(records, fold_candidates, fold_actionable, fold_opportunities)))
    return full, tuple(fold_metrics)
