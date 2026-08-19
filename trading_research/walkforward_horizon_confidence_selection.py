"""Causal walk-forward selection of a predefined horizon-confidence threshold."""
from __future__ import annotations
from statistics import mean
from typing import Sequence

from .data import Bar
from .horizon_confidence_ablation import evaluate_horizon_confidence_ablation
from .online_horizon_expert_ensemble import evaluate_online_horizon_expert_ensemble

THRESHOLDS = (0.0, 1.0, 2.0, 4.0)
FOLDS = 4


def _score(values: dict[str, object]) -> float:
    return float(values.get("mean_net_return_bps", -1e9))


def evaluate_walkforward_horizon_confidence_selection(
    bars: Sequence[Bar], *, thresholds: Sequence[float] = THRESHOLDS,
    folds: int = FOLDS, transaction_cost_bps: float = 4.0,
    half_life: float = 60.0, min_history: int = 120,
) -> dict[str, object]:
    thresholds = tuple(float(v) for v in thresholds)
    if not thresholds or folds < 2:
        raise ValueError("invalid parameters")
    n = len(bars)
    fold_size = n // folds
    fold_results: list[dict[str, object]] = []
    for fold in range(1, folds):
        train_end = fold * fold_size
        test_end = n if fold == folds - 1 else (fold + 1) * fold_size
        train = bars[:train_end]
        test = bars[train_end:test_end]
        # Evaluate each fixed threshold on the pre-fold training segment.
        train_ablation = evaluate_horizon_confidence_ablation(
            train, thresholds=thresholds, transaction_cost_bps=transaction_cost_bps,
            half_life=half_life, min_history=min_history, folds=4,
        )
        train_results = train_ablation["results"]
        selected = max(thresholds, key=lambda t: _score(train_results[str(t)]))
        # Apply only the selected threshold to the unseen next fold.
        test_ablation = evaluate_horizon_confidence_ablation(
            test, thresholds=(selected,), transaction_cost_bps=transaction_cost_bps,
            half_life=half_life, min_history=min_history, folds=1,
        )
        test_result = test_ablation["results"][str(selected)]
        fold_results.append({
            "fold": fold,
            "train_range": [0, train_end],
            "test_range": [train_end, test_end],
            "selected_threshold": selected,
            "train_threshold_scores": {str(t): _score(train_results[str(t)]) for t in thresholds},
            "test": test_result,
        })
    return {
        "policy": "causal_walkforward_horizon_confidence_selection",
        "thresholds": thresholds,
        "folds": fold_results,
        "selection_rule": "Each threshold is selected using only completed outcomes from the preceding training segment; the next segment is completely unseen at selection time.",
        "causal_rule": "All expert, horizon and confidence information is decision-time/current-past state; future returns are evaluation-only.",
    }
