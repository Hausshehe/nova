"""Evaluate a small predefined causal directional policy family.

This is a diagnostic, not an optimizer: policies and parameters are fixed in code
before evaluation and future labels are never used to choose a policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices


@dataclass(frozen=True)
class PolicyMetrics:
    policy: str
    decisions: int
    mean_return_bps: float
    mean_net_return_bps: float
    positive_net_rate: float
    fold_net_returns: tuple[float, ...]
    folds_positive: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sma_direction(closes: Sequence[float], index: int) -> str | None:
    if index < 49:
        return None
    fast = mean(closes[index - 19:index + 1])
    slow = mean(closes[index - 49:index + 1])
    if fast == slow:
        return None
    return "LONG" if fast > slow else "SHORT"


def _momentum_direction(closes: Sequence[float], index: int, horizon: int) -> str | None:
    if index < horizon:
        return None
    move = closes[index] / closes[index - horizon] - 1.0
    if move == 0:
        return None
    return "LONG" if move > 0 else "SHORT"


def _policy_direction(closes: Sequence[float], index: int, policy: str) -> str | None:
    sma = _sma_direction(closes, index)
    if sma is None:
        return None
    if policy == "sma_both":
        return sma
    if policy == "sma_long_only":
        return "LONG" if sma == "LONG" else None
    if policy == "sma_short_only":
        return "SHORT" if sma == "SHORT" else None
    if policy == "sma_mom4_agree":
        mom = _momentum_direction(closes, index, 4)
        return sma if mom == sma else None
    if policy == "sma_mom8_agree":
        mom = _momentum_direction(closes, index, 8)
        return sma if mom == sma else None
    raise ValueError(f"unknown policy: {policy}")


def evaluate_directional_policy_family(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    transaction_cost_bps: float = 4.0,
    folds: int = 4,
) -> tuple[PolicyMetrics, ...]:
    if future_bars <= 0 or folds <= 0:
        raise ValueError("future_bars and folds must be positive")
    candidates = high_recall_candidate_indices(bars, fast_period=20, slow_period=50)
    closes = [b.close for b in bars]
    policies = (
        "sma_both",
        "sma_long_only",
        "sma_short_only",
        "sma_mom4_agree",
        "sma_mom8_agree",
    )
    fold_size = len(bars) // folds
    results: list[PolicyMetrics] = []

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
                direction = _policy_direction(closes, index, policy)
                if direction is None:
                    continue
                raw = (closes[index + future_bars] / closes[index] - 1.0) * 10_000.0
                signed = raw if direction == "LONG" else -raw
                returns.append(signed)
                fold_values.append(signed - transaction_cost_bps)
            fold_net.append(mean(fold_values) if fold_values else 0.0)
        net = [value - transaction_cost_bps for value in returns]
        results.append(PolicyMetrics(
            policy=policy,
            decisions=len(returns),
            mean_return_bps=mean(returns) if returns else 0.0,
            mean_net_return_bps=mean(net) if net else 0.0,
            positive_net_rate=sum(v > 0 for v in net) / len(net) if net else 0.0,
            fold_net_returns=tuple(fold_net),
            folds_positive=sum(v > 0 for v in fold_net),
        ))
    return tuple(results)
