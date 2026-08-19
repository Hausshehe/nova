"""Measure whether AI escalation requests are justified by subsequent moves."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .data import Bar
from .escalation import AdaptiveEscalator
from .market_monitor import MarketMonitor, MarketSnapshot


@dataclass(frozen=True)
class EscalationEfficiencyReport:
    ai_requests: int
    justified_ai_requests: int
    unnecessary_ai_requests: int
    precision: float
    future_opportunities: int
    recalled_opportunities: int
    recall: float


def evaluate_efficiency(
    bars: Sequence[Bar],
    *,
    symbol: str = "EURUSD",
    timeframe: str = "15m",
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    escalator: AdaptiveEscalator | None = None,
) -> EscalationEfficiencyReport:
    """Measure escalation precision and opportunity recall on historical bars.

    A review is considered justified when a move of at least
    ``opportunity_move_bps`` occurs within the next ``future_bars`` bars.
    This is diagnostic only; it must never be used as a live trading signal.
    """
    if future_bars <= 0:
        raise ValueError("future_bars must be positive")
    if opportunity_move_bps <= 0:
        raise ValueError("opportunity_move_bps must be positive")
    if not bars:
        return EscalationEfficiencyReport(0, 0, 0, 0.0, 0, 0, 0.0)

    ordered = tuple(bars)
    monitor = MarketMonitor()
    escalator = escalator or AdaptiveEscalator()
    ai_indices: set[int] = set()

    for index, bar in enumerate(ordered):
        events = monitor.observe(
            MarketSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                bar=bar,
                previous_bar=ordered[index - 1] if index else None,
            )
        )
        if any(escalator.evaluate(event).request_ai for event in events):
            ai_indices.add(index)

    justified = 0
    opportunities = 0
    recalled = 0
    for index, bar in enumerate(ordered):
        future = ordered[index + 1 : index + 1 + future_bars]
        if not future:
            continue
        opportunity = any(
            abs(next_bar.close / bar.close - 1.0) * 10_000.0 >= opportunity_move_bps
            for next_bar in future
        )
        if opportunity:
            opportunities += 1
        if index in ai_indices and opportunity:
            justified += 1

    for index in range(len(ordered)):
        future = ordered[index + 1 : index + 1 + future_bars]
        if not future:
            continue
        opportunity = any(
            abs(next_bar.close / ordered[index].close - 1.0) * 10_000.0 >= opportunity_move_bps
            for next_bar in future
        )
        if opportunity and any(index - future_bars <= ai <= index for ai in ai_indices):
            recalled += 1

    ai_requests = len(ai_indices)
    precision = justified / ai_requests if ai_requests else 0.0
    recall = recalled / opportunities if opportunities else 0.0
    return EscalationEfficiencyReport(
        ai_requests=ai_requests,
        justified_ai_requests=justified,
        unnecessary_ai_requests=max(0, ai_requests - justified),
        precision=precision,
        future_opportunities=opportunities,
        recalled_opportunities=recalled,
        recall=recall,
    )
