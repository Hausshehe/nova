"""Causal online ensemble of fixed directional experts.

Each completed historical outcome is incorporated exactly once, at the first
future decision where its horizon has fully elapsed. Expert weights therefore
reflect genuine online history rather than repeated re-processing.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices

EXPERTS = (
    "sma",
    "mom4",
    "mom8",
    "mom12",
    "contrarian4",
    "contrarian8",
    "long_only",
    "short_only",
)


@dataclass(frozen=True)
class EnsemblePrediction:
    index: int
    expert: str
    direction: str
    score: float
    net_return_bps: float


def _sma_direction(closes: Sequence[float], index: int) -> str | None:
    if index < 49:
        return None
    fast = mean(closes[index - 19:index + 1])
    slow = mean(closes[index - 49:index + 1])
    if fast == slow:
        return None
    return "LONG" if fast > slow else "SHORT"


def _momentum(closes: Sequence[float], index: int, horizon: int) -> str | None:
    if index < horizon:
        return None
    move = closes[index] / closes[index - horizon] - 1.0
    if move == 0:
        return None
    return "LONG" if move > 0 else "SHORT"


def _direction(closes: Sequence[float], index: int, expert: str) -> str | None:
    if expert == "sma":
        return _sma_direction(closes, index)
    if expert == "mom4":
        return _momentum(closes, index, 4)
    if expert == "mom8":
        return _momentum(closes, index, 8)
    if expert == "mom12":
        return _momentum(closes, index, 12)
    if expert == "contrarian4":
        direction = _momentum(closes, index, 4)
        return None if direction is None else ("SHORT" if direction == "LONG" else "LONG")
    if expert == "contrarian8":
        direction = _momentum(closes, index, 8)
        return None if direction is None else ("SHORT" if direction == "LONG" else "LONG")
    if expert == "long_only":
        return "LONG"
    if expert == "short_only":
        return "SHORT"
    raise ValueError(f"unknown expert: {expert}")


def evaluate_online_expert_ensemble(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    transaction_cost_bps: float = 4.0,
    half_life: float = 60.0,
    min_history: int = 120,
    folds: int = 4,
    evaluation_start_index: int = 0,
) -> dict[str, object]:
    if (
        future_bars <= 0
        or half_life <= 0
        or min_history < 0
        or folds <= 0
        or evaluation_start_index < 0
        or evaluation_start_index > len(bars)
    ):
        raise ValueError("invalid parameters")

    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    evaluation_candidates = [index for index in candidates if index >= evaluation_start_index]
    closes = [bar.close for bar in bars]
    scores = {expert: 0.0 for expert in EXPERTS}
    observations = {expert: 0 for expert in EXPERTS}
    predictions: list[EnsemblePrediction] = []
    fold_values: list[list[float]] = [[] for _ in range(folds)]
    decay = exp(-1.0 / half_life)

    # Advance through all historical candidate outcomes exactly once. This
    # includes development history and, causally, completed final-test outcomes
    # that become available before later final-test decisions.
    next_completed = 0
    for index in candidates:
        cutoff = index - future_bars
        while next_completed < len(candidates) and candidates[next_completed] <= cutoff:
            historical_index = candidates[next_completed]
            next_completed += 1
            if historical_index + future_bars >= len(bars):
                continue
            raw = (closes[historical_index + future_bars] / closes[historical_index] - 1.0) * 10_000.0
            for expert in EXPERTS:
                direction = _direction(closes, historical_index, expert)
                if direction is None:
                    continue
                signed = raw if direction == "LONG" else -raw
                net = signed - transaction_cost_bps
                scores[expert] = decay * scores[expert] + (1.0 - decay) * net
                observations[expert] += 1

        if index < evaluation_start_index:
            continue
        if min(observations.values()) < min_history:
            continue

        ranked = sorted(EXPERTS, key=lambda expert: scores[expert], reverse=True)
        best, second = ranked[0], ranked[1]
        if scores[best] <= 0.0:
            continue

        direction = _direction(closes, index, best)
        if direction is None or index + future_bars >= len(bars):
            continue

        raw = (closes[index + future_bars] / closes[index] - 1.0) * 10_000.0
        signed = raw if direction == "LONG" else -raw
        net = signed - transaction_cost_bps
        test_length = max(1, len(bars) - evaluation_start_index)
        fold = min(folds - 1, (index - evaluation_start_index) * folds // test_length)
        fold_values[fold].append(net)
        predictions.append(
            EnsemblePrediction(
                index=index,
                expert=best,
                direction=direction,
                score=scores[best] - scores[second],
                net_return_bps=net,
            )
        )

    nets = [prediction.net_return_bps for prediction in predictions]
    fold_net = [mean(values) if values else 0.0 for values in fold_values]
    return {
        "policy": "causal_online_expert_ensemble",
        "experts": EXPERTS,
        "candidate_bars": len(evaluation_candidates),
        "decisions": len(predictions),
        "decision_rate": len(predictions) / len(evaluation_candidates) if evaluation_candidates else 0.0,
        "mean_net_return_bps": mean(nets) if nets else 0.0,
        "positive_net_rate": sum(value > 0 for value in nets) / len(nets) if nets else 0.0,
        "fold_net_returns": fold_net,
        "folds_positive": sum(value > 0 for value in fold_net),
        "parameters": {
            "future_bars": future_bars,
            "transaction_cost_bps": transaction_cost_bps,
            "half_life": half_life,
            "min_history": min_history,
            "folds": folds,
            "evaluation_start_index": evaluation_start_index,
        },
        "causal_rule": "Each completed expert outcome is incorporated once, only after its horizon completes; final-test outcomes may influence only later final-test decisions.",
    }
