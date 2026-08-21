"""Causal conditional-edge gate for a fixed set of directional experts.

The policy asks whether an expert has enough context-specific evidence to
justify a trade. It shrinks sparse context estimates toward a global causal
estimate, applies an uncertainty penalty, and otherwise abstains.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, sqrt
from statistics import mean, median
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .online_expert_ensemble import EXPERTS, _direction

CONTEXTS = tuple(
    f"{trend}|{volatility}|{momentum}"
    for trend in ("up", "down")
    for volatility in ("lowvol", "highvol")
    for momentum in ("up", "down")
)


@dataclass
class _WeightedStats:
    weight: float = 0.0
    weight_sq: float = 0.0
    mean: float = 0.0
    second_moment: float = 0.0
    observations: int = 0

    def update(self, value: float, decay: float) -> None:
        self.weight *= decay
        self.weight_sq *= decay * decay
        self.mean *= decay
        self.second_moment *= decay
        self.weight += 1.0
        self.weight_sq += 1.0
        alpha = 1.0 / self.weight
        self.mean += alpha * (value - self.mean)
        self.second_moment += alpha * (value * value - self.second_moment)
        self.observations += 1

    @property
    def effective_n(self) -> float:
        if self.weight_sq <= 0.0:
            return 0.0
        return self.weight * self.weight / self.weight_sq

    @property
    def variance(self) -> float:
        return max(0.0, self.second_moment - self.mean * self.mean)


def _context(closes: Sequence[float], index: int) -> str | None:
    if index < 99:
        return None
    fast = mean(closes[index - 19:index + 1])
    slow = mean(closes[index - 49:index + 1])
    if fast == slow:
        return None

    returns = [closes[i] / closes[i - 1] - 1.0 for i in range(index - 19, index + 1)]
    current_vol = sqrt(mean(value * value for value in returns))
    historical_vols = []
    for end in range(index - 49, index + 1):
        window = [closes[i] / closes[i - 1] - 1.0 for i in range(end - 19, end + 1)]
        historical_vols.append(sqrt(mean(value * value for value in window)))
    volatility = "highvol" if current_vol >= median(historical_vols) else "lowvol"
    momentum = "up" if closes[index] > closes[index - 4] else "down"
    trend = "up" if fast > slow else "down"
    return f"{trend}|{volatility}|{momentum}"


def _shrunken_estimate(
    context_stats: _WeightedStats,
    global_stats: _WeightedStats,
    prior: float,
) -> tuple[float, float, float]:
    n = context_stats.effective_n
    g_n = global_stats.effective_n
    if n <= 0.0 or g_n <= 0.0:
        return global_stats.mean, global_stats.variance, 0.0
    context_weight = n / (n + prior)
    estimate = context_weight * context_stats.mean + (1.0 - context_weight) * global_stats.mean
    variance = context_weight * context_stats.variance + (1.0 - context_weight) * global_stats.variance
    return estimate, variance, n


def evaluate_conditional_edge_gate(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    transaction_cost_bps: float = 4.0,
    half_life: float = 60.0,
    min_context_history: int = 40,
    min_global_history: int = 120,
    shrinkage_prior: float = 30.0,
    z_score: float = 1.0,
    min_edge_bps: float = 0.5,
    min_margin_bps: float = 0.5,
    folds: int = 4,
    evaluation_start_index: int = 0,
) -> dict[str, object]:
    if future_bars <= 0 or half_life <= 0 or min_context_history < 0 or min_global_history < 0:
        raise ValueError("invalid parameters")
    if shrinkage_prior < 0 or z_score < 0 or min_edge_bps < 0 or min_margin_bps < 0:
        raise ValueError("invalid gate parameters")

    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    evaluation_candidates = [index for index in candidates if index >= evaluation_start_index]
    closes = [bar.close for bar in bars]
    decay = exp(-1.0 / half_life)
    global_stats = {expert: _WeightedStats() for expert in EXPERTS}
    context_stats = {
        context: {expert: _WeightedStats() for expert in EXPERTS}
        for context in CONTEXTS
    }
    next_completed = 0
    fold_values: list[list[float]] = [[] for _ in range(folds)]
    decisions = 0
    abstentions = 0
    context_counts = {context: 0 for context in CONTEXTS}
    predictions: list[dict[str, object]] = []

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
                global_stats[expert].update(net, decay)
                context_stats[historical_context][expert].update(net, decay)

        if index < evaluation_start_index:
            continue
        current_context = _context(closes, index)
        if current_context is None or min(stat.observations for stat in global_stats.values()) < min_global_history:
            continue

        candidates_for_context = []
        if all(context_stats[current_context][expert].observations >= min_context_history for expert in EXPERTS):
            for expert in EXPERTS:
                estimate, variance, n = _shrunken_estimate(
                    context_stats[current_context][expert], global_stats[expert], shrinkage_prior
                )
                uncertainty = z_score * sqrt(variance / max(n, 1.0))
                candidates_for_context.append((expert, estimate - uncertainty, estimate, uncertainty))
        else:
            for expert in EXPERTS:
                stats = global_stats[expert]
                uncertainty = z_score * sqrt(stats.variance / max(stats.effective_n, 1.0))
                candidates_for_context.append((expert, stats.mean - uncertainty, stats.mean, uncertainty))

        ranked = sorted(candidates_for_context, key=lambda item: item[1], reverse=True)
        best, best_lcb, best_estimate, best_uncertainty = ranked[0]
        second_lcb = ranked[1][1]
        if best_lcb <= min_edge_bps or best_lcb - second_lcb <= min_margin_bps:
            abstentions += 1
            continue

        direction = _direction(closes, index, best)
        if direction is None or index + future_bars >= len(bars):
            abstentions += 1
            continue
        raw = (closes[index + future_bars] / closes[index] - 1.0) * 10_000.0
        signed = raw if direction == "LONG" else -raw
        net = signed - transaction_cost_bps
        test_length = max(1, len(bars) - evaluation_start_index)
        fold = min(folds - 1, (index - evaluation_start_index) * folds // test_length)
        fold_values[fold].append(net)
        decisions += 1
        context_counts[current_context] += 1
        predictions.append(
            {
                "index": index,
                "context": current_context,
                "expert": best,
                "direction": direction,
                "lower_confidence_bps": best_lcb,
                "estimate_bps": best_estimate,
                "uncertainty_bps": best_uncertainty,
                "net_return_bps": net,
            }
        )

    nets = [float(row["net_return_bps"]) for row in predictions]
    fold_net = [mean(values) if values else 0.0 for values in fold_values]
    return {
        "policy": "causal_conditional_edge_gate",
        "experts": EXPERTS,
        "contexts": CONTEXTS,
        "candidate_bars": len(evaluation_candidates),
        "decisions": decisions,
        "abstentions": abstentions,
        "decision_rate": decisions / len(evaluation_candidates) if evaluation_candidates else 0.0,
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
            "shrinkage_prior": shrinkage_prior,
            "z_score": z_score,
            "min_edge_bps": min_edge_bps,
            "min_margin_bps": min_margin_bps,
            "folds": folds,
            "evaluation_start_index": evaluation_start_index,
        },
        "causal_rule": "Completed outcomes are incorporated only after their horizon completes; no final-test outcome is available before its horizon completes.",
    }
