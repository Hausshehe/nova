"""Causal directional baseline evaluation for the trusted candidate set.

This is deliberately deterministic. It does not train or optimize a model and
it does not execute trades. Direction is supplied by the decision-time SMA-gap
sign, while future movement is used only as an evaluation label.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean, median
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .outcome_ledger import build_outcome_ledger


@dataclass(frozen=True)
class DirectionalBaselineMetrics:
    candidate_bars: int
    evaluated_bars: int
    directional_bars: int
    long_bars: int
    short_bars: int
    direction_accuracy: float
    mean_signed_move_bps: float
    median_signed_move_bps: float
    mean_net_signed_move_bps: float
    positive_net_rate: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _metrics(records, indices: set[int], transaction_cost_bps: float) -> DirectionalBaselineMetrics:
    selected = [
        r for r in records
        if r.index in indices
        and not r.insufficient_future_window
        and r.sma_gap_bps is not None
        and r.sma_gap_bps != 0
        and r.directional_return_bps is not None
    ]
    signed: list[float] = []
    longs = shorts = 0
    correct = 0
    for record in selected:
        # The SMA sign is the decision-time direction. The terminal close
        # return over the fixed horizon is the only directional performance
        # label. Intrahorizon excursions are intentionally not used here.
        if record.sma_gap_bps > 0:
            longs += 1
            move = record.directional_return_bps
        else:
            shorts += 1
            move = record.directional_return_bps
        signed.append(move)
        if move > 0:
            correct += 1

    net = [move - transaction_cost_bps for move in signed]
    return DirectionalBaselineMetrics(
        candidate_bars=len(indices),
        evaluated_bars=len(selected),
        directional_bars=len(selected),
        long_bars=longs,
        short_bars=shorts,
        direction_accuracy=correct / len(selected) if selected else 0.0,
        mean_signed_move_bps=mean(signed) if signed else 0.0,
        median_signed_move_bps=median(signed) if signed else 0.0,
        mean_net_signed_move_bps=mean(net) if net else 0.0,
        positive_net_rate=sum(value > 0 for value in net) / len(net) if net else 0.0,
    )


def evaluate_directional_baseline(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    transaction_cost_bps: float = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
    folds: int = 4,
) -> tuple[DirectionalBaselineMetrics, tuple[tuple[int, DirectionalBaselineMetrics], ...]]:
    """Evaluate SMA-gap direction using terminal causal-horizon returns."""
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
    full = _metrics(records, candidates, transaction_cost_bps)

    n = len(bars)
    fold_size = n // folds
    fold_metrics: list[tuple[int, DirectionalBaselineMetrics]] = []
    for fold in range(folds):
        start = fold * fold_size
        end = n if fold == folds - 1 else (fold + 1) * fold_size
        fold_candidates = {i for i in candidates if start <= i < end}
        fold_metrics.append((fold + 1, _metrics(records, fold_candidates, transaction_cost_bps)))
    return full, tuple(fold_metrics)
