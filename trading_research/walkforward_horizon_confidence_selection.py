"""Causal walk-forward selection of a predefined horizon-confidence threshold."""
from __future__ import annotations

from math import exp
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .online_expert_ensemble import EXPERTS, _direction
from .online_horizon_expert_ensemble import HORIZONS

THRESHOLDS = (0.0, 1.0, 2.0, 4.0)
FOLDS = 4


def evaluate_walkforward_horizon_confidence_selection(
    bars: Sequence[Bar], *, thresholds: Sequence[float] = THRESHOLDS,
    folds: int = FOLDS, transaction_cost_bps: float = 4.0,
    half_life: float = 60.0, min_history: int = 120,
) -> dict[str, object]:
    thresholds = tuple(float(v) for v in thresholds)
    if not thresholds or any(v < 0 for v in thresholds) or folds < 2 or half_life <= 0 or min_history < 0:
        raise ValueError("invalid parameters")

    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    closes = [b.close for b in bars]
    keys = [(expert, horizon) for expert in EXPERTS for horizon in HORIZONS]
    scores = {key: 0.0 for key in keys}
    observations = {key: 0 for key in keys}
    completed = {h: 0 for h in HORIZONS}
    decay = exp(-1.0 / half_life)
    fold_size = len(bars) // folds
    fold_results: list[dict[str, object]] = []

    def update_history(index: int) -> None:
        for horizon in HORIZONS:
            cutoff = index - horizon
            while completed[horizon] < len(candidates) and candidates[completed[horizon]] <= cutoff:
                j = candidates[completed[horizon]]
                completed[horizon] += 1
                if j + horizon >= len(bars):
                    continue
                raw = (closes[j + horizon] / closes[j] - 1.0) * 10_000.0
                for expert in EXPERTS:
                    direction = _direction(closes, j, expert)
                    if direction is None:
                        continue
                    signed = raw if direction == "LONG" else -raw
                    key = (expert, horizon)
                    net = signed - transaction_cost_bps
                    scores[key] = decay * scores[key] + (1.0 - decay) * net
                    observations[key] += 1

    all_records: list[dict[str, float | int]] = []
    for i in candidates:
        update_history(i)
        eligible = [k for k in keys if observations[k] >= min_history]
        if len(eligible) < 2:
            continue
        ranked = sorted(eligible, key=lambda k: scores[k], reverse=True)
        best, second = ranked[0], ranked[1]
        expert, horizon = best
        direction = _direction(closes, i, expert)
        if direction is None or i + horizon >= len(bars):
            continue
        raw = (closes[i + horizon] / closes[i] - 1.0) * 10_000.0
        signed = raw if direction == "LONG" else -raw
        net = signed - transaction_cost_bps
        all_records.append({"index": i, "edge": scores[best], "margin": scores[best] - scores[second], "net": net})

    for fold in range(1, folds):
        train_end = fold * fold_size
        test_end = len(bars) if fold == folds - 1 else (fold + 1) * fold_size
        train_records = [r for r in all_records if r["index"] < train_end]
        test_records = [r for r in all_records if train_end <= r["index"] < test_end]
        train_scores = {}
        for threshold in thresholds:
            values = [float(r["net"]) for r in train_records if float(r["edge"]) >= threshold and float(r["margin"]) >= threshold]
            train_scores[str(threshold)] = mean(values) if values else -1e9
        selected = max(thresholds, key=lambda t: train_scores[str(t)])
        test_values = [float(r["net"]) for r in test_records if float(r["edge"]) >= selected and float(r["margin"]) >= selected]
        fold_results.append({
            "fold": fold,
            "train_range": [0, train_end],
            "test_range": [train_end, test_end],
            "selected_threshold": selected,
            "train_threshold_mean_net_bps": train_scores,
            "test_decisions": len(test_values),
            "test_mean_net_return_bps": mean(test_values) if test_values else 0.0,
            "test_positive_net_rate": sum(v > 0 for v in test_values) / len(test_values) if test_values else 0.0,
            "test_passes_net_floor": mean(test_values) > 0.0 if test_values else False,
        })

    return {
        "policy": "causal_walkforward_horizon_confidence_selection",
        "thresholds": thresholds,
        "folds": fold_results,
        "selection_rule": "Each threshold is selected only from completed outcomes strictly before the unseen test segment; test outcomes cannot influence threshold selection.",
        "causal_rule": "Expert, horizon, edge and margin use only completed pre-decision outcomes; future returns are evaluation-only.",
    }
