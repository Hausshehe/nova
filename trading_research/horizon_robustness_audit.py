"""Frozen robustness diagnostics for the current 8-bar research clue.

This audit deliberately does not search for a better parameter. It freezes
causal decisions at one research configuration, then asks whether the signal
survives simple baselines, changing costs, temporal folds, and non-overlapping
holding periods.

Important: these are *decision/outcome* diagnostics, not a claim of executable
portfolio PnL. A separate execution simulator is required before any trading
conclusion is made.
"""
from __future__ import annotations

from statistics import mean, median, pstdev
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .online_expert_ensemble import EXPERTS, _direction
from .online_horizon_expert_ensemble import HORIZONS, HorizonPrediction, collect_online_horizon_predictions

DEFAULT_COST_GRID = (0.0, 2.0, 4.0, 6.0, 8.0)
DEFAULT_FOLDS = 4


def _fold(index: int, bar_count: int, folds: int) -> int:
    return min(folds - 1, index * folds // bar_count)


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _summary(
    predictions: Sequence[HorizonPrediction],
    *,
    bar_count: int,
    folds: int,
    evaluation_cost_bps: float,
) -> dict[str, object]:
    gross = [prediction.gross_return_bps for prediction in predictions]
    net = [value - evaluation_cost_bps for value in gross]
    fold_values: list[list[float]] = [[] for _ in range(folds)]
    for prediction, value in zip(predictions, net):
        fold_values[_fold(prediction.index, bar_count, folds)].append(value)
    fold_means = [mean(values) if values else 0.0 for values in fold_values]
    return {
        "decisions": len(predictions),
        "mean_gross_return_bps": mean(gross) if gross else 0.0,
        "median_gross_return_bps": median(gross) if gross else 0.0,
        "gross_stddev_bps": pstdev(gross) if len(gross) > 1 else 0.0,
        "mean_net_return_bps": mean(net) if net else 0.0,
        "median_net_return_bps": median(net) if net else 0.0,
        "positive_net_rate": sum(value > 0 for value in net) / len(net) if net else 0.0,
        "sum_net_return_bps": sum(net),
        "return_percentiles_bps": {
            "p10": _percentile(gross, 0.10),
            "p25": _percentile(gross, 0.25),
            "p75": _percentile(gross, 0.75),
            "p90": _percentile(gross, 0.90),
        },
        "fold_net_returns_bps": fold_means,
        "folds_positive": sum(value > 0 for value in fold_means),
        "worst_fold_net_return_bps": min(fold_means) if fold_means else 0.0,
        "best_fold_net_return_bps": max(fold_means) if fold_means else 0.0,
        "evaluation_cost_bps": evaluation_cost_bps,
    }


def _fixed_expert_predictions(
    bars: Sequence[Bar],
    *,
    expert: str,
    horizon: int,
) -> tuple[HorizonPrediction, ...]:
    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    closes = [bar.close for bar in bars]
    predictions: list[HorizonPrediction] = []
    for index in candidates:
        direction = _direction(closes, index, expert)
        if direction is None or index + horizon >= len(bars):
            continue
        raw = (closes[index + horizon] / closes[index] - 1.0) * 10_000.0
        signed = raw if direction == "LONG" else -raw
        predictions.append(
            HorizonPrediction(
                index=index,
                expert=expert,
                horizon=horizon,
                direction=direction,
                score=0.0,
                gross_return_bps=signed,
            )
        )
    return tuple(predictions)


def _non_overlapping(predictions: Sequence[HorizonPrediction]) -> tuple[HorizonPrediction, ...]:
    accepted: list[HorizonPrediction] = []
    next_available = -1
    for prediction in sorted(predictions, key=lambda item: item.index):
        if prediction.index < next_available:
            continue
        accepted.append(prediction)
        next_available = prediction.index + prediction.horizon
    return tuple(accepted)


def _cost_sensitivity(
    predictions: Sequence[HorizonPrediction],
    *,
    bar_count: int,
    folds: int,
    cost_grid_bps: Sequence[float],
) -> dict[str, object]:
    return {
        str(cost): _summary(
            predictions,
            bar_count=bar_count,
            folds=folds,
            evaluation_cost_bps=float(cost),
        )
        for cost in cost_grid_bps
    }


def _configuration(
    bars: Sequence[Bar],
    predictions: Sequence[HorizonPrediction],
    *,
    training_cost_bps: float,
    folds: int,
    cost_grid_bps: Sequence[float],
) -> dict[str, object]:
    baseline = _summary(
        predictions,
        bar_count=len(bars),
        folds=folds,
        evaluation_cost_bps=training_cost_bps,
    )
    non_overlap = _non_overlapping(predictions)
    baseline["non_overlapping"] = _summary(
        non_overlap,
        bar_count=len(bars),
        folds=folds,
        evaluation_cost_bps=training_cost_bps,
    )
    baseline["cost_sensitivity"] = _cost_sensitivity(
        predictions,
        bar_count=len(bars),
        folds=folds,
        cost_grid_bps=cost_grid_bps,
    )
    baseline["non_overlapping_decisions"] = len(non_overlap)
    return baseline


def audit_fixed_8_vs_alternatives(
    bars: Sequence[Bar],
    *,
    training_cost_bps: float = 4.0,
    cost_grid_bps: Sequence[float] = DEFAULT_COST_GRID,
    half_life: float = 60.0,
    min_history: int = 120,
    folds: int = DEFAULT_FOLDS,
) -> dict[str, object]:
    """Run a frozen comparison without tuning or re-selecting on test data."""
    if len(bars) < 3:
        raise ValueError("at least three bars are required")
    if training_cost_bps < 0 or half_life <= 0 or min_history < 0 or folds <= 0:
        raise ValueError("invalid parameters")
    cost_grid = tuple(float(value) for value in cost_grid_bps)
    if not cost_grid or any(value < 0 for value in cost_grid):
        raise ValueError("cost_grid_bps must contain non-negative values")

    fixed_8 = collect_online_horizon_predictions(
        bars,
        horizons=(8,),
        training_cost_bps=training_cost_bps,
        half_life=half_life,
        min_history=min_history,
    )
    adaptive = collect_online_horizon_predictions(
        bars,
        horizons=HORIZONS,
        training_cost_bps=training_cost_bps,
        half_life=half_life,
        min_history=min_history,
    )

    configurations: dict[str, dict[str, object]] = {
        "online_expert_fixed_8": _configuration(
            bars, fixed_8, training_cost_bps=training_cost_bps, folds=folds, cost_grid_bps=cost_grid
        ),
        "online_expert_adaptive_2_4_8": _configuration(
            bars, adaptive, training_cost_bps=training_cost_bps, folds=folds, cost_grid_bps=cost_grid
        ),
    }

    for expert in EXPERTS:
        fixed_expert = _fixed_expert_predictions(bars, expert=expert, horizon=8)
        configurations[f"fixed_expert_{expert}_8"] = _configuration(
            bars, fixed_expert, training_cost_bps=training_cost_bps, folds=folds, cost_grid_bps=cost_grid
        )

    return {
        "policy": "frozen_horizon_robustness_audit",
        "research_status": "diagnostic_only",
        "training_cost_bps": training_cost_bps,
        "cost_grid_bps": cost_grid,
        "folds": folds,
        "candidate_count": len(high_recall_candidate_indices(bars, fast_period=20, slow_period=50)),
        "configurations": configurations,
        "interpretation_guardrail": "Decision-level signed returns are not executable portfolio PnL; overlapping predictions are reported separately from a non-overlapping holding diagnostic.",
        "anti_overfitting_rule": "Decision streams are selected once using the fixed training cost and then re-evaluated across the cost grid without changing decisions.",
        "causality_rule": "All online selections use only outcomes whose individual forecast horizons completed before each decision.",
    }
