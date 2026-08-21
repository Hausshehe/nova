"""Causal contextual online ensemble of fixed directional experts.

Expert performance is learned separately for the current SMA regime, while a
small global history provides a causal fallback until enough regime-specific
history exists. No future label is used before its horizon completes.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .online_expert_ensemble import EXPERTS, _direction


@dataclass(frozen=True)
class ContextualPrediction:
    index: int
    context: str
    expert: str
    direction: str
    score: float
    net_return_bps: float


def _context(closes: Sequence[float], index: int) -> str | None:
    if index < 49:
        return None
    fast = mean(closes[index - 19:index + 1])
    slow = mean(closes[index - 49:index + 1])
    if fast == slow:
        return None
    return "uptrend" if fast > slow else "downtrend"


def evaluate_contextual_online_expert_ensemble(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    transaction_cost_bps: float = 4.0,
    half_life: float = 60.0,
    min_context_history: int = 30,
    min_global_history: int = 120,
    folds: int = 4,
    evaluation_start_index: int = 0,
) -> dict[str, object]:
    if (
        future_bars <= 0
        or half_life <= 0
        or min_context_history < 0
        or min_global_history < 0
        or folds <= 0
        or evaluation_start_index < 0
        or evaluation_start_index > len(bars)
    ):
        raise ValueError("invalid parameters")

    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    evaluation_candidates = [index for index in candidates if index >= evaluation_start_index]
    closes = [bar.close for bar in bars]
    decay = exp(-1.0 / half_life)
    global_scores = {expert: 0.0 for expert in EXPERTS}
    global_obs = {expert: 0 for expert in EXPERTS}
    context_scores = {
        context: {expert: 0.0 for expert in EXPERTS}
        for context in ("uptrend", "downtrend")
    }
    context_obs = {
        context: {expert: 0 for expert in EXPERTS}
        for context in ("uptrend", "downtrend")
    }
    next_completed = 0
    predictions: list[ContextualPrediction] = []
    fold_values: list[list[float]] = [[] for _ in range(folds)]
    context_counts = {"uptrend": 0, "downtrend": 0, "global_fallback": 0}

    # Learn from all completed outcomes in chronological order. Development
    # history initializes the selector; final-test outcomes can only influence
    # later final-test decisions after their four-bar horizon completes.
    for index in candidates:
        cutoff = index - future_bars
        while next_completed < len(candidates) and candidates[next_completed] <= cutoff:
            historical_index = candidates[next_completed]
            next_completed += 1
            if historical_index + future_bars >= len(bars):
                continue
            historical_context = _context(closes, historical_index)
            if historical_context is None:
                continue
            raw = (closes[historical_index + future_bars] / closes[historical_index] - 1.0) * 10_000.0
            for expert in EXPERTS:
                direction = _direction(closes, historical_index, expert)
                if direction is None:
                    continue
                signed = raw if direction == "LONG" else -raw
                net = signed - transaction_cost_bps
                global_scores[expert] = decay * global_scores[expert] + (1.0 - decay) * net
                global_obs[expert] += 1
                context_scores[historical_context][expert] = (
                    decay * context_scores[historical_context][expert]
                    + (1.0 - decay) * net
                )
                context_obs[historical_context][expert] += 1

        if index < evaluation_start_index:
            continue
        current_context = _context(closes, index)
        if current_context is None or min(global_obs.values()) < min_global_history:
            continue

        contextual_ready = min(context_obs[current_context].values()) >= min_context_history
        scores = context_scores[current_context] if contextual_ready else global_scores
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
        context_counts[current_context if contextual_ready else "global_fallback"] += 1
        predictions.append(
            ContextualPrediction(
                index=index,
                context=current_context,
                expert=best,
                direction=direction,
                score=scores[best] - scores[second],
                net_return_bps=net,
            )
        )

    nets = [prediction.net_return_bps for prediction in predictions]
    fold_net = [mean(values) if values else 0.0 for values in fold_values]
    return {
        "policy": "causal_contextual_online_expert_ensemble",
        "experts": EXPERTS,
        "candidate_bars": len(evaluation_candidates),
        "decisions": len(predictions),
        "decision_rate": len(predictions) / len(evaluation_candidates) if evaluation_candidates else 0.0,
        "mean_net_return_bps": mean(nets) if nets else 0.0,
        "positive_net_rate": sum(value > 0 for value in nets) / len(nets) if nets else 0.0,
        "fold_net_returns": fold_net,
        "folds_positive": sum(value > 0 for value in fold_net),
        "context_decisions": context_counts,
        "parameters": {
            "future_bars": future_bars,
            "transaction_cost_bps": transaction_cost_bps,
            "half_life": half_life,
            "min_context_history": min_context_history,
            "min_global_history": min_global_history,
            "folds": folds,
            "evaluation_start_index": evaluation_start_index,
        },
        "causal_rule": "Each completed expert outcome is incorporated once into global and regime-specific histories; final-test outcomes may influence only later final-test decisions.",
    }
