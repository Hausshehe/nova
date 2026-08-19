"""Causal regime-conditioned directional learner.

This deliberately replaces the failed fixed logistic learner with a simpler,
more interpretable adaptive method. Regimes are defined only from current/past
features. For each unseen fold, direction is chosen from historical signed
outcomes observed strictly before that fold. Future outcomes are never used at
decision time.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .outcome_ledger import build_outcome_ledger


@dataclass(frozen=True)
class RegimePrediction:
    index: int
    regime: tuple[int, int, int, int]
    direction: str
    expected_return_bps: float
    net_return_bps: float


def _feature_signs(bars: Sequence[Bar], index: int) -> tuple[int, int, int, int]:
    closes = [b.close for b in bars]
    gap = 0.0
    if index >= 49:
        fast = mean(closes[index - 19:index + 1])
        slow = mean(closes[index - 49:index + 1])
        gap = (fast / slow - 1.0) * 10_000.0 if slow else 0.0
    m4 = (closes[index] / closes[index - 4] - 1.0) * 10_000.0 if index >= 4 else 0.0
    m8 = (closes[index] / closes[index - 8] - 1.0) * 10_000.0 if index >= 8 else 0.0
    m12 = (closes[index] / closes[index - 12] - 1.0) * 10_000.0 if index >= 12 else 0.0
    return tuple(1 if x > 0 else -1 if x < 0 else 0 for x in (gap, m4, m8, m12))  # type: ignore[return-value]


def evaluate_walkforward_regime_direction(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    transaction_cost_bps: float = 4.0,
    folds: int = 4,
    min_train: int = 240,
) -> dict[str, object]:
    # Build labels once for evaluation; they are never consulted for the current
    # fold until the corresponding observation belongs to the training past.
    build_outcome_ledger(bars, future_bars=future_bars, transaction_cost_bps_round_trip=transaction_cost_bps)
    candidates = high_recall_candidate_indices(bars, fast_period=20, slow_period=50)
    predictions: list[RegimePrediction] = []
    fold_net: list[float] = []
    n = len(bars)
    fold_size = n // folds

    for fold in range(folds):
        start = fold * fold_size
        end = n if fold == folds - 1 else (fold + 1) * fold_size
        test_indices = sorted(i for i in candidates if start <= i < end and i + future_bars < n)
        train_indices = [i for i in range(49, start) if i + future_bars < start]
        if len(train_indices) < min_train:
            fold_net.append(0.0)
            continue

        # Each regime stores the historical signed four-bar return and count.
        # A global mean supplies deterministic shrinkage for sparse regimes.
        global_returns: list[float] = []
        buckets: dict[tuple[int, int, int, int], list[float]] = {}
        for i in train_indices:
            raw = (bars[i + future_bars].close / bars[i].close - 1.0) * 10_000.0
            global_returns.append(raw)
            buckets.setdefault(_feature_signs(bars, i), []).append(raw)
        global_mean = mean(global_returns) if global_returns else 0.0

        fold_values: list[float] = []
        for i in test_indices:
            regime = _feature_signs(bars, i)
            values = buckets.get(regime, [])
            # Fixed empirical-Bayes smoothing: five virtual observations at the
            # global mean prevents tiny regimes from dominating direction.
            expected = (sum(values) + 5.0 * global_mean) / (len(values) + 5.0)
            direction = "LONG" if expected >= 0.0 else "SHORT"
            raw = (bars[i + future_bars].close / bars[i].close - 1.0) * 10_000.0
            signed = raw if direction == "LONG" else -raw
            net = signed - transaction_cost_bps
            fold_values.append(net)
            predictions.append(RegimePrediction(i, regime, direction, expected, net))
        fold_net.append(mean(fold_values) if fold_values else 0.0)

    nets = [p.net_return_bps for p in predictions]
    return {
        "policy": "causal_walkforward_regime_direction",
        "decisions": len(predictions),
        "mean_net_return_bps": mean(nets) if nets else 0.0,
        "positive_net_rate": sum(v > 0 for v in nets) / len(nets) if nets else 0.0,
        "fold_net_returns": fold_net,
        "folds_positive": sum(v > 0 for v in fold_net),
        "predictions": tuple(p.__dict__ for p in predictions),
        "causal_rule": "Regime and direction use only current/past features and completed pre-fold labels; future outcomes are evaluation-only.",
    }
