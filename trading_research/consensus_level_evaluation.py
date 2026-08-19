"""Causal side-by-side evaluation of natural expert consensus levels."""
from __future__ import annotations
from statistics import mean
from typing import Sequence
from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .consensus_direction_policy import EXPERTS, _direction

LEVELS = (4, 5)


def evaluate_consensus_levels(
    bars: Sequence[Bar], *, future_bars: int = 4,
    transaction_cost_bps: float = 4.0, folds: int = 4,
) -> dict[str, object]:
    if future_bars <= 0 or folds <= 0:
        raise ValueError("invalid parameters")
    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    closes = [b.close for b in bars]
    outputs: dict[str, dict[str, object]] = {}
    for level in LEVELS:
        nets_by_fold: list[list[float]] = [[] for _ in range(folds)]
        agreements = []
        for i in candidates:
            votes = [_direction(closes, i, e) for e in EXPERTS]
            long_votes = sum(v == "LONG" for v in votes)
            short_votes = sum(v == "SHORT" for v in votes)
            agreement = max(long_votes, short_votes)
            if agreement < level or i + future_bars >= len(bars):
                continue
            direction = "LONG" if long_votes > short_votes else "SHORT"
            raw = (closes[i + future_bars] / closes[i] - 1.0) * 10_000.0
            signed = raw if direction == "LONG" else -raw
            net = signed - transaction_cost_bps
            fold = min(folds - 1, i * folds // len(bars))
            nets_by_fold[fold].append(net)
            agreements.append(agreement)
        nets = [v for fold in nets_by_fold for v in fold]
        fold_net = [mean(v) if v else 0.0 for v in nets_by_fold]
        outputs[str(level)] = {
            "decisions": len(nets),
            "decision_rate": len(nets) / len(candidates) if candidates else 0.0,
            "mean_net_return_bps": mean(nets) if nets else 0.0,
            "positive_net_rate": sum(v > 0 for v in nets) / len(nets) if nets else 0.0,
            "fold_net_returns": fold_net,
            "folds_positive": sum(v > 0 for v in fold_net),
            "agreement_observations": len(agreements),
        }
    return {
        "policy": "causal_natural_consensus_level_comparison",
        "candidate_bars": len(candidates),
        "levels_tested": LEVELS,
        "experts": EXPERTS,
        "selection_rule": "Levels are predefined and evaluated side-by-side; no future labels select a level.",
        "results": outputs,
        "causal_rule": "Consensus and direction use current/past prices only; future close movement is evaluation-only.",
    }
