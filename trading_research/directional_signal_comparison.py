"""Compare predefined causal direction signals without parameter optimization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices


@dataclass(frozen=True)
class SignalMetrics:
    signal: str
    decisions: int
    mean_return_bps: float
    mean_net_return_bps: float
    positive_net_rate: float
    chronological_fold_net_returns: tuple[float, ...]
    folds_positive: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _signal_direction(closes: Sequence[float], index: int, signal: str) -> str | None:
    if signal == "sma20_50":
        if index < 49:
            return None
        fast = mean(closes[index - 19:index + 1])
        slow = mean(closes[index - 49:index + 1])
        if fast == slow:
            return None
        return "LONG" if fast > slow else "SHORT"
    horizon = int(signal.removeprefix("momentum"))
    if index < horizon:
        return None
    move = closes[index] / closes[index - horizon] - 1.0
    if move == 0:
        return None
    return "LONG" if move > 0 else "SHORT"


def compare_directional_signals(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    transaction_cost_bps: float = 4.0,
    folds: int = 4,
) -> tuple[SignalMetrics, ...]:
    if future_bars <= 0 or folds <= 0:
        raise ValueError("future_bars and folds must be positive")
    candidates = high_recall_candidate_indices(bars, fast_period=20, slow_period=50)
    closes = [b.close for b in bars]
    signals = ("sma20_50", "momentum4", "momentum8", "momentum12")
    fold_size = len(bars) // folds
    results: list[SignalMetrics] = []

    for signal in signals:
        returns: list[float] = []
        fold_net: list[float] = []
        for fold in range(folds):
            start = fold * fold_size
            end = len(bars) if fold == folds - 1 else (fold + 1) * fold_size
            fold_returns: list[float] = []
            for index in sorted(candidates):
                if not start <= index < end or index + future_bars >= len(bars):
                    continue
                direction = _signal_direction(closes, index, signal)
                if direction is None:
                    continue
                raw = (closes[index + future_bars] / closes[index] - 1.0) * 10_000.0
                signed = raw if direction == "LONG" else -raw
                returns.append(signed)
                fold_returns.append(signed - transaction_cost_bps)
            fold_net.append(mean(fold_returns) if fold_returns else 0.0)
        net = [r - transaction_cost_bps for r in returns]
        results.append(SignalMetrics(
            signal=signal,
            decisions=len(returns),
            mean_return_bps=mean(returns) if returns else 0.0,
            mean_net_return_bps=mean(net) if net else 0.0,
            positive_net_rate=sum(v > 0 for v in net) / len(net) if net else 0.0,
            chronological_fold_net_returns=tuple(fold_net),
            folds_positive=sum(v > 0 for v in fold_net),
        ))
    return tuple(results)
