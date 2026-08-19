"""Causal directional baseline for the research lab.

This is deliberately deterministic and report-only. Direction is chosen from
current/past information (fast/slow SMA relationship). Future bars are used
only to score the decision after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Sequence

from .data import Bar


@dataclass(frozen=True)
class DirectionalOutcome:
    index: int
    direction: str
    entry_close: float
    future_close: float
    directional_return_bps: float
    net_return_bps: float
    favorable_excursion_bps: float
    adverse_excursion_bps: float
    hit_cost_adjusted_target: bool


def _sma(values: Sequence[float], period: int) -> float:
    return mean(values[-period:])


def build_directional_outcomes(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    target_bps: float = 30.0,
    transaction_cost_bps_round_trip: float = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
) -> tuple[DirectionalOutcome, ...]:
    """Generate causal SMA-direction decisions and future-only outcomes."""
    if future_bars <= 0:
        raise ValueError("future_bars must be positive")
    if fast_period <= 0 or slow_period <= 0:
        raise ValueError("SMA periods must be positive")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be smaller than slow_period")
    if target_bps <= 0:
        raise ValueError("target_bps must be positive")
    if transaction_cost_bps_round_trip < 0:
        raise ValueError("transaction cost cannot be negative")

    min_index = slow_period - 1
    last_index = len(bars) - future_bars - 1
    outcomes: list[DirectionalOutcome] = []
    for index in range(min_index, max(min_index, last_index + 1)):
        fast = _sma([bar.close for bar in bars[: index + 1]], fast_period)
        slow = _sma([bar.close for bar in bars[: index + 1]], slow_period)
        direction = "LONG" if fast >= slow else "SHORT"
        entry = bars[index].close
        future = bars[index + future_bars].close
        sign = 1.0 if direction == "LONG" else -1.0
        directional_return_bps = sign * (future - entry) / entry * 10_000.0

        future_slice = bars[index + 1 : index + future_bars + 1]
        favorable = [sign * (bar.high - entry) / entry * 10_000.0 if sign > 0 else sign * (bar.low - entry) / entry * 10_000.0 for bar in future_slice]
        adverse = [sign * (bar.low - entry) / entry * 10_000.0 if sign > 0 else sign * (bar.high - entry) / entry * 10_000.0 for bar in future_slice]
        favorable_excursion_bps = max(favorable) if favorable else 0.0
        adverse_excursion_bps = min(adverse) if adverse else 0.0
        net_return_bps = directional_return_bps - transaction_cost_bps_round_trip
        outcomes.append(
            DirectionalOutcome(
                index=index,
                direction=direction,
                entry_close=entry,
                future_close=future,
                directional_return_bps=directional_return_bps,
                net_return_bps=net_return_bps,
                favorable_excursion_bps=favorable_excursion_bps,
                adverse_excursion_bps=adverse_excursion_bps,
                hit_cost_adjusted_target=favorable_excursion_bps >= target_bps + transaction_cost_bps_round_trip,
            )
        )
    return tuple(outcomes)


def summarize_directional_outcomes(outcomes: Sequence[DirectionalOutcome]) -> dict[str, float | int]:
    """Return compact report metrics; no execution or trade-state mutation."""
    if not outcomes:
        return {
            "decisions": 0,
            "long_decisions": 0,
            "short_decisions": 0,
            "mean_return_bps": 0.0,
            "mean_net_return_bps": 0.0,
            "positive_net_rate": 0.0,
            "target_hit_rate": 0.0,
        }
    net = [item.net_return_bps for item in outcomes]
    return {
        "decisions": len(outcomes),
        "long_decisions": sum(item.direction == "LONG" for item in outcomes),
        "short_decisions": sum(item.direction == "SHORT" for item in outcomes),
        "mean_return_bps": mean(item.directional_return_bps for item in outcomes),
        "mean_net_return_bps": mean(net),
        "positive_net_rate": sum(value > 0 for value in net) / len(net),
        "target_hit_rate": sum(item.hit_cost_adjusted_target for item in outcomes) / len(outcomes),
    }
