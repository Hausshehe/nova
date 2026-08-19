"""Small fixed-rule causal learner for directional research.

No future label is available when a prediction is made. The learner is trained
only on completed observations strictly before the prediction index.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp
from statistics import mean
from typing import Sequence

from .data import Bar
from .outcome_ledger import build_outcome_ledger
from .high_recall_candidate_policy import high_recall_candidate_indices


@dataclass(frozen=True)
class AdaptivePrediction:
    index: int
    probability_long: float
    direction: str
    raw_return_bps: float
    net_return_bps: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _features(bars: Sequence[Bar], index: int) -> tuple[float, float, float, float]:
    closes = [b.close for b in bars]
    gap = 0.0
    if index >= 49:
        fast = mean(closes[index - 19:index + 1])
        slow = mean(closes[index - 49:index + 1])
        gap = (fast / slow - 1.0) * 10_000.0 if slow else 0.0
    m4 = (closes[index] / closes[index - 4] - 1.0) * 10_000.0 if index >= 4 else 0.0
    m8 = (closes[index] / closes[index - 8] - 1.0) * 10_000.0 if index >= 8 else 0.0
    m12 = (closes[index] / closes[index - 12] - 1.0) * 10_000.0 if index >= 12 else 0.0
    return gap, m4, m8, m12


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = exp(-x)
        return 1.0 / (1.0 + z)
    z = exp(x)
    return z / (1.0 + z)


def _fit_ridge_logistic(rows: list[tuple[tuple[float, ...], int]]) -> tuple[float, ...]:
    # Fixed, deterministic online-friendly batch learner. Seven fixed epochs,
    # learning rate 0.02, L2 penalty 0.01. No hyperparameter selection.
    if not rows:
        return (0.0,) * 5
    w = [0.0] * 5
    lr = 0.02
    l2 = 0.01
    for _ in range(7):
        grad = [0.0] * 5
        for x, y in rows:
            z = sum(w[j] * x[j] for j in range(5))
            p = _sigmoid(z)
            for j in range(5):
                grad[j] += (p - y) * x[j]
        scale = 1.0 / len(rows)
        for j in range(5):
            grad[j] = grad[j] * scale + l2 * w[j]
            w[j] -= lr * grad[j]
    return tuple(w)


def evaluate_walkforward_adaptive_direction(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    transaction_cost_bps: float = 4.0,
    folds: int = 4,
    min_train: int = 240,
) -> dict[str, object]:
    records = build_outcome_ledger(bars, future_bars=future_bars, transaction_cost_bps_round_trip=transaction_cost_bps)
    candidates = high_recall_candidate_indices(bars, fast_period=20, slow_period=50)
    predictions: list[AdaptivePrediction] = []
    fold_net: list[float] = []
    n = len(bars)
    fold_size = n // folds

    for fold in range(folds):
        start = fold * fold_size
        end = n if fold == folds - 1 else (fold + 1) * fold_size
        test_indices = sorted(i for i in candidates if start <= i < end and i + future_bars < n)
        train_indices = [i for i in range(max(0, start)) if i >= 49 and i + future_bars < start]
        if len(train_indices) < min_train:
            fold_net.append(0.0)
            continue
        train_rows: list[tuple[tuple[float, ...], int]] = []
        for i in train_indices:
            raw = (bars[i + future_bars].close / bars[i].close - 1.0) * 10_000.0
            y = 1 if raw > 0 else 0
            gap, m4, m8, m12 = _features(bars, i)
            scale = (20.0, 20.0, 20.0, 20.0)
            x = (1.0, gap / scale[0], m4 / scale[1], m8 / scale[2], m12 / scale[3])
            train_rows.append((x, y))
        w = _fit_ridge_logistic(train_rows)
        fold_values: list[float] = []
        for i in test_indices:
            gap, m4, m8, m12 = _features(bars, i)
            x = (1.0, gap / 20.0, m4 / 20.0, m8 / 20.0, m12 / 20.0)
            p_long = _sigmoid(sum(w[j] * x[j] for j in range(5)))
            direction = "LONG" if p_long >= 0.5 else "SHORT"
            raw = (bars[i + future_bars].close / bars[i].close - 1.0) * 10_000.0
            signed = raw if direction == "LONG" else -raw
            net = signed - transaction_cost_bps
            fold_values.append(net)
            predictions.append(AdaptivePrediction(i, p_long, direction, signed, net))
        fold_net.append(mean(fold_values) if fold_values else 0.0)

    nets = [p.net_return_bps for p in predictions]
    return {
        "policy": "causal_walkforward_adaptive_direction",
        "decisions": len(predictions),
        "mean_net_return_bps": mean(nets) if nets else 0.0,
        "positive_net_rate": sum(v > 0 for v in nets) / len(nets) if nets else 0.0,
        "fold_net_returns": fold_net,
        "folds_positive": sum(v > 0 for v in fold_net),
        "predictions": tuple(p.to_dict() for p in predictions),
        "causal_rule": "Each fold is trained only on completed pre-fold observations; future returns are labels only.",
    }
