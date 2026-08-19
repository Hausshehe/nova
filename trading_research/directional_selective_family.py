"""Evaluate a small predefined causal directional selectivity family.

This is a diagnostic, not an optimizer. Policies are fixed before evaluation,
and future labels are used only for scoring.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices


@dataclass(frozen=True)
class SelectivePolicyMetrics:
    policy: str
    decisions: int
    mean_return_bps: float
    mean_net_return_bps: float
    positive_net_rate: float
    fold_net_returns: tuple[float, ...]
    folds_positive: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sma_state(closes: Sequence[float], index: int) -> tuple[str, float] | None:
    if index < 49:
        return None
    fast = mean(closes[index - 19:index + 1])
    slow = mean(closes[index - 49:index + 1])
    if fast == slow or slow == 0:
        return None
    direction = "LONG" if fast > slow else "SHORT"
    gap_bps = abs(fast / slow - 1.0) * 10_000.0
    return direction, gap_bps


def _direction(closes: Sequence[float], index: int, policy: str) -> str | None:
    state = _sma_state(closes, index)
    if state is None:
        return None
    direction, gap_bps = state
    if policy == "short_gap_ge_20":
        return "SHORT" if direction == "SHORT" and gap_bps >= 20.0 else None
    if policy == "short_gap_lt_20":
        return "SHORT" if direction == "SHORT" and gap_bps < 20.0 else None
    if policy == "both_gap_ge_20":
        return direction if gap_bps >= 20.0 else None
    if policy == "both_gap_lt_20":
        return direction if gap_bps < 20.0 else None
    if policy == "short_gap_ge_40":
        return "SHORT" if direction == "SHORT" and gap_bps >= 40.0 else None
    raise ValueError(f"unknown policy: {policy}")


def evaluate_directional_selective_family(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    transaction_cost_bps: float = 4.0,
    folds: int = 4,
) -> tuple[SelectivePolicyMetrics, ...]:
    if future_bars <= 0 or folds <= 0:
        raise ValueError("future_bars and folds must be positive")

    candidates = high_recall_candidate_indices(bars, fast_period=20, slow_period=50)
    closes = [b.close for b in bars]
    policies = (
        "short_gap_ge_20",
        "short_gap_lt_20",
        "both_gap_ge_20",
        "both_gap_lt_20",
        "short_gap_ge_40",
    )
    fold_size = len(bars) // folds
    results: list[SelectivePolicyMetrics] = []

    for policy in policies:
        returns: list[float] = []
        fold_net: list[float] = []
        for fold in range(folds):
            start = fold * fold_size
            end = len(bars) if fold == folds - 1 else (fold + 1) * fold_size
            fold_values: list[float] = []
            for index in sorted(candidates):
                if not start <= index < end or index + future_bars >= len(bars):
                    continue
                direction = _direction(closes, index, policy)
                if direction is None:
                    continue
                raw = (closes[index + future_bars] / closes[index] - 1.0) * 10_000.0
                signed = raw if direction == "LONG" else -raw
                returns.append(signed)
                fold_values.append(signed - transaction_cost_bps)
            fold_net.append(mean(fold_values) if fold_values else 0.0)

        net = [value - transaction_cost_bps for value in returns]
        results.append(
            SelectivePolicyMetrics(
                policy=policy,
                decisions=len(returns),
                mean_return_bps=mean(returns) if returns else 0.0,
                mean_net_return_bps=mean(net) if net else 0.0,
                positive_net_rate=sum(v > 0 for v in net) / len(net) if net else 0.0,
                fold_net_returns=tuple(fold_net),
                folds_positive=sum(v > 0 for v in fold_net),
            )
        )
    return tuple(results)
