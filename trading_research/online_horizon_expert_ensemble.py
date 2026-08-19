"""Causal online ensemble that learns both expert and holding horizon.

This module separates *decision selection* from *outcome costing*: the
online selector only sees outcomes whose own horizons have completed, while
callers may evaluate the frozen decision stream under different cost
assumptions without silently re-training the selector.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .online_expert_ensemble import EXPERTS, _direction

HORIZONS = (2, 4, 8)


@dataclass(frozen=True)
class HorizonPrediction:
    index: int
    expert: str
    horizon: int
    direction: str
    score: float
    gross_return_bps: float


def collect_online_horizon_predictions(
    bars: Sequence[Bar],
    *,
    horizons: Sequence[int] = HORIZONS,
    training_cost_bps: float = 4.0,
    half_life: float = 60.0,
    min_history: int = 120,
) -> tuple[HorizonPrediction, ...]:
    """Collect a frozen causal decision stream.

    The selector is updated only with outcomes whose forecast horizon has
    completely elapsed. ``training_cost_bps`` affects selector state, but it
    is deliberately separate from later evaluation costs so robustness tests
    can hold decisions fixed while varying assumed execution costs.
    """
    horizons = tuple(horizons)
    if not horizons or any(h <= 0 for h in horizons):
        raise ValueError("horizons must contain positive integers")
    if training_cost_bps < 0 or half_life <= 0 or min_history < 0:
        raise ValueError("invalid parameters")

    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    closes = [bar.close for bar in bars]
    keys = [(expert, horizon) for expert in EXPERTS for horizon in horizons]
    scores = {key: 0.0 for key in keys}
    observations = {key: 0 for key in keys}
    completed = {horizon: 0 for horizon in horizons}
    predictions: list[HorizonPrediction] = []
    decay = exp(-1.0 / half_life)

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
                    net = signed - training_cost_bps
                    key = (expert, horizon)
                    scores[key] = decay * scores[key] + (1.0 - decay) * net
                    observations[key] += 1

        eligible = [key for key in keys if observations[key] >= min_history]
        if len(eligible) < 2:
            continue
        ranked = sorted(eligible, key=lambda key: scores[key], reverse=True)
        best, second = ranked[0], ranked[1]
        if scores[best] <= 0.0:
            continue

        expert, horizon = best
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
                score=scores[best] - scores[second],
                gross_return_bps=signed,
            )
        )

    return tuple(predictions)


def evaluate_online_horizon_expert_ensemble(
    bars: Sequence[Bar], *, horizons: Sequence[int] = HORIZONS,
    transaction_cost_bps: float = 4.0, half_life: float = 60.0,
    min_history: int = 120, folds: int = 4,
) -> dict[str, object]:
    if transaction_cost_bps < 0 or folds <= 0:
        raise ValueError("invalid parameters")

    predictions = collect_online_horizon_predictions(
        bars,
        horizons=horizons,
        training_cost_bps=transaction_cost_bps,
        half_life=half_life,
        min_history=min_history,
    )
    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    nets = [prediction.gross_return_bps - transaction_cost_bps for prediction in predictions]
    fold_values: list[list[float]] = [[] for _ in range(folds)]
    for prediction, net in zip(predictions, nets):
        fold = min(folds - 1, prediction.index * folds // len(bars))
        fold_values[fold].append(net)

    fold_net = [mean(values) if values else 0.0 for values in fold_values]
    return {
        "policy": "causal_online_horizon_expert_ensemble",
        "experts": EXPERTS,
        "horizons": tuple(horizons),
        "candidate_bars": len(candidates),
        "decisions": len(predictions),
        "decision_rate": len(predictions) / len(candidates) if candidates else 0.0,
        "mean_net_return_bps": mean(nets) if nets else 0.0,
        "positive_net_rate": sum(value > 0 for value in nets) / len(nets) if nets else 0.0,
        "fold_net_returns": fold_net,
        "folds_positive": sum(value > 0 for value in fold_net),
        "selected_horizon_counts": {
            str(h): sum(prediction.horizon == h for prediction in predictions)
            for h in tuple(horizons)
        },
        "selected_expert_counts": {
            expert: sum(prediction.expert == expert for prediction in predictions)
            for expert in EXPERTS
        },
        "parameters": {
            "transaction_cost_bps": transaction_cost_bps,
            "half_life": half_life,
            "min_history": min_history,
            "folds": folds,
        },
        "causal_rule": "Expert and holding horizon are selected only from outcomes whose own horizons completed before the decision; future outcomes are evaluation-only.",
    }
