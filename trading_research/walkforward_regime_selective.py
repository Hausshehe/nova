"""Causal recency-weighted selective regime learner.

This is a deliberate method change, not another tuning pass on the failed
logistic learner. It adapts to regime drift with exponentially decayed
historical evidence and abstains when the learned directional edge is too
small to justify transaction costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices


@dataclass(frozen=True)
class SelectivePrediction:
    index: int
    direction: str
    expected_return_bps: float
    net_return_bps: float


def _features(bars: Sequence[Bar], index: int) -> tuple[int, int, int, int]:
    closes = [b.close for b in bars]
    gap = 0.0
    if index >= 49:
        fast = mean(closes[index - 19:index + 1])
        slow = mean(closes[index - 49:index + 1])
        gap = (fast / slow - 1.0) * 10_000.0 if slow else 0.0
    values = [
        gap,
        (closes[index] / closes[index - 4] - 1.0) * 10_000.0 if index >= 4 else 0.0,
        (closes[index] / closes[index - 8] - 1.0) * 10_000.0 if index >= 8 else 0.0,
        (closes[index] / closes[index - 12] - 1.0) * 10_000.0 if index >= 12 else 0.0,
    ]
    return tuple(1 if x > 0 else -1 if x < 0 else 0 for x in values)  # type: ignore[return-value]


def evaluate_walkforward_selective_regime(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    transaction_cost_bps: float = 4.0,
    folds: int = 4,
    min_train: int = 240,
    half_life: int = 80,
    entry_threshold_bps: float = 5.0,
) -> dict[str, object]:
    candidates = high_recall_candidate_indices(bars, fast_period=20, slow_period=50)
    predictions: list[SelectivePrediction] = []
    fold_net: list[float] = []
    fold_decisions: list[int] = []
    n = len(bars)
    fold_size = n // folds

    for fold in range(folds):
        start = fold * fold_size
        end = n if fold == folds - 1 else (fold + 1) * fold_size
        test_indices = sorted(i for i in candidates if start <= i < end and i + future_bars < n)
        train_indices = [i for i in range(49, start) if i + future_bars < start]
        if len(train_indices) < min_train:
            fold_net.append(0.0)
            fold_decisions.append(0)
            continue

        latest = train_indices[-1]
        buckets: dict[tuple[int, int, int, int], list[tuple[float, float]]] = {}
        global_values: list[tuple[float, float]] = []
        for i in train_indices:
            age = latest - i
            weight = exp(-0.69314718056 * age / max(1, half_life))
            raw = (bars[i + future_bars].close / bars[i].close - 1.0) * 10_000.0
            item = (raw, weight)
            global_values.append(item)
            buckets.setdefault(_features(bars, i), []).append(item)

        def weighted(values: list[tuple[float, float]]) -> float:
            total_w = sum(w for _, w in values)
            if not total_w:
                return 0.0
            return sum(v * w for v, w in values) / total_w

        global_mean = weighted(global_values)
        fold_values: list[float] = []
        for i in test_indices:
            values = buckets.get(_features(bars, i), [])
            # Recency-weighted regime estimate with a small global prior.
            regime_mean = weighted(values) if values else global_mean
            sample_weight = sum(w for _, w in values)
            prior_strength = 2.0
            expected = (regime_mean * sample_weight + global_mean * prior_strength) / (sample_weight + prior_strength)
            if abs(expected) < entry_threshold_bps:
                continue
            direction = "LONG" if expected > 0 else "SHORT"
            raw = (bars[i + future_bars].close / bars[i].close - 1.0) * 10_000.0
            signed = raw if direction == "LONG" else -raw
            net = signed - transaction_cost_bps
            fold_values.append(net)
            predictions.append(SelectivePrediction(i, direction, expected, net))
        fold_net.append(mean(fold_values) if fold_values else 0.0)
        fold_decisions.append(len(fold_values))

    nets = [p.net_return_bps for p in predictions]
    return {
        "policy": "causal_walkforward_selective_recency_regime",
        "candidate_bars": len(candidates),
        "decisions": len(predictions),
        "decision_rate": len(predictions) / len(candidates) if candidates else 0.0,
        "mean_net_return_bps": mean(nets) if nets else 0.0,
        "positive_net_rate": sum(v > 0 for v in nets) / len(nets) if nets else 0.0,
        "fold_net_returns": fold_net,
        "fold_decisions": fold_decisions,
        "folds_positive": sum(v > 0 for v in fold_net),
        "parameters": {"half_life": half_life, "entry_threshold_bps": entry_threshold_bps},
        "causal_rule": "Recency-weighted regime evidence uses only completed pre-fold outcomes; future outcomes are evaluation-only.",
    }
