"""Causal ablation for confidence/edge gating on the adaptive horizon ensemble."""
from __future__ import annotations

from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .online_expert_ensemble import EXPERTS, _direction
from .online_horizon_expert_ensemble import HORIZONS
from math import exp


def evaluate_horizon_confidence_ablation(
    bars: Sequence[Bar], *, thresholds: Sequence[float] = (0.0, 1.0, 2.0, 4.0),
    horizons: Sequence[int] = HORIZONS, transaction_cost_bps: float = 4.0,
    half_life: float = 60.0, min_history: int = 120, folds: int = 4,
) -> dict[str, object]:
    thresholds = tuple(float(t) for t in thresholds)
    horizons = tuple(horizons)
    if not thresholds or any(t < 0 for t in thresholds) or not horizons or any(h <= 0 for h in horizons):
        raise ValueError("invalid thresholds or horizons")
    if half_life <= 0 or min_history < 0 or folds <= 0:
        raise ValueError("invalid parameters")

    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    closes = [bar.close for bar in bars]
    keys = [(expert, horizon) for expert in EXPERTS for horizon in horizons]
    scores = {key: 0.0 for key in keys}
    observations = {key: 0 for key in keys}
    completed = {h: 0 for h in horizons}
    decay = exp(-1.0 / half_life)
    nets_by_threshold = {t: [] for t in thresholds}
    folds_by_threshold = {t: [[] for _ in range(folds)] for t in thresholds}
    decisions_by_threshold = {t: 0 for t in thresholds}

    for index in candidates:
        for horizon in horizons:
            cutoff = index - horizon
            while completed[horizon] < len(candidates) and candidates[completed[horizon]] <= cutoff:
                historical_index = candidates[completed[horizon]]
                completed[horizon] += 1
                if historical_index + horizon >= len(bars):
                    continue
                raw = (closes[historical_index + horizon] / closes[historical_index] - 1.0) * 10_000.0
                for expert in EXPERTS:
                    direction = _direction(closes, historical_index, expert)
                    if direction is None:
                        continue
                    signed = raw if direction == "LONG" else -raw
                    key = (expert, horizon)
                    scores[key] = decay * scores[key] + (1.0 - decay) * (signed - transaction_cost_bps)
                    observations[key] += 1

        eligible = [k for k in keys if observations[k] >= min_history]
        if len(eligible) < 2:
            continue
        ranked = sorted(eligible, key=lambda k: scores[k], reverse=True)
        best, second = ranked[0], ranked[1]
        edge = scores[best]
        margin = scores[best] - scores[second]
        expert, horizon = best
        direction = _direction(closes, index, expert)
        if direction is None or index + horizon >= len(bars):
            continue
        raw = (closes[index + horizon] / closes[index] - 1.0) * 10_000.0
        signed = raw if direction == "LONG" else -raw
        net = signed - transaction_cost_bps
        fold = min(folds - 1, index * folds // len(bars))
        for threshold in thresholds:
            if edge < threshold or margin < threshold:
                continue
            decisions_by_threshold[threshold] += 1
            nets_by_threshold[threshold].append(net)
            folds_by_threshold[threshold][fold].append(net)

    results = {}
    for threshold in thresholds:
        nets = nets_by_threshold[threshold]
        fold_values = folds_by_threshold[threshold]
        fold_net = [mean(v) if v else 0.0 for v in fold_values]
        results[str(threshold)] = {
            "threshold_bps": threshold,
            "decisions": decisions_by_threshold[threshold],
            "decision_rate": decisions_by_threshold[threshold] / len(candidates) if candidates else 0.0,
            "mean_net_return_bps": mean(nets) if nets else 0.0,
            "positive_net_rate": sum(v > 0 for v in nets) / len(nets) if nets else 0.0,
            "fold_net_returns": fold_net,
            "folds_positive": sum(v > 0 for v in fold_net),
        }
    return {
        "policy": "causal_horizon_confidence_ablation",
        "thresholds_bps": thresholds,
        "selection_rule": "Thresholds are predefined and evaluated side-by-side; no future outcome selects a threshold.",
        "results": results,
        "parameters": {"horizons": horizons, "transaction_cost_bps": transaction_cost_bps, "half_life": half_life, "min_history": min_history, "folds": folds},
        "causal_rule": "Expert, horizon, edge and margin use only outcomes completed before the decision; future outcomes are evaluation-only.",
    }
