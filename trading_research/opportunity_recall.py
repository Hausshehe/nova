"""Measure whether escalation sees potentially important moves early enough."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .data import Bar
from .escalation import AdaptiveEscalator, EscalationDecision
from .market_monitor import MarketMonitor, MarketSnapshot


@dataclass(frozen=True)
class OpportunityRecallReport:
    opportunities: int
    opportunities_with_ai_review: int
    recall: float
    ai_requests: int
    missed_opportunities: int


def evaluate_opportunity_recall(
    bars: Sequence[Bar],
    *,
    symbol: str = "EURUSD",
    timeframe: str = "15m",
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    monitor: MarketMonitor | None = None,
    escalator: AdaptiveEscalator | None = None,
) -> OpportunityRecallReport:
    """Replay bars and measure AI-review recall for future price opportunities.

    An opportunity is a bar whose close-to-future-close absolute move reaches
    ``opportunity_move_bps`` within ``future_bars``. An AI review counts as
    timely when an escalation request occurs on the opportunity bar itself or
    within the preceding ``future_bars`` bars.

    This is a diagnostic metric, not a trading-performance metric. It exists
    specifically to detect overly strict escalation rules that could make Nova
    miss developing opportunities.
    """
    if future_bars <= 0:
        raise ValueError("future_bars must be positive")
    if opportunity_move_bps <= 0:
        raise ValueError("opportunity_move_bps must be positive")
    if not bars:
        return OpportunityRecallReport(0, 0, 0.0, 0, 0)

    ordered = tuple(bars)
    monitor = monitor or MarketMonitor()
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
        for event in events:
            decision: EscalationDecision = escalator.evaluate(event)
            if decision.request_ai:
                ai_indices.add(index)

    opportunities = 0
    detected = 0
    for index, bar in enumerate(ordered):
        future = ordered[index + 1 : index + 1 + future_bars]
        if not future:
            continue
        target = max(abs(next_bar.close / bar.close - 1.0) * 10_000.0 for next_bar in future)
        if target < opportunity_move_bps:
            continue
        opportunities += 1
        review_start = max(0, index - future_bars)
        if any(review_start <= review <= index for review in ai_indices):
            detected += 1

    recall = detected / opportunities if opportunities else 0.0
    return OpportunityRecallReport(
        opportunities=opportunities,
        opportunities_with_ai_review=detected,
        recall=recall,
        ai_requests=len(ai_indices),
        missed_opportunities=opportunities - detected,
    )
