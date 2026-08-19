"""High-recall candidate routing for Nova's trading research gate.

This policy is intentionally conservative: it forms the AI-review candidate
set from the union of independent causal evidence paths and deduplicates at
one decision per bar. It does not optimize, suppress, or execute trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .data import Bar
from .market_monitor import MarketMonitor
from .strategy_escalation_bridge import StrategyEscalationDecision, evaluate_strategy_escalation


@dataclass(frozen=True)
class HighRecallCandidate:
    index: int
    request_ai: bool
    evidence: tuple[str, ...]


def build_high_recall_candidates(
    bars: Sequence[Bar],
    *,
    timeframe: str = "15m",
    fast_period: int = 20,
    slow_period: int = 50,
) -> tuple[HighRecallCandidate, ...]:
    """Return one conservative AI candidate decision per bar.

    A bar is a candidate when either the bounded market escalation path or the
    strategy-hint path requests AI review. The paths are unioned rather than
    intersected so strategy evidence cannot be discarded by market cooldowns.
    """
    if not bars:
        return ()

    events = MarketMonitor().observe_history("EURUSD", timeframe, bars)
    decisions = evaluate_strategy_escalation(
        bars,
        events,
        fast_period=fast_period,
        slow_period=slow_period,
    )

    by_index: dict[int, list[StrategyEscalationDecision]] = {}
    for decision in decisions:
        by_index.setdefault(decision.index, []).append(decision)

    candidates: list[HighRecallCandidate] = []
    for index in range(len(bars)):
        evidence: list[str] = []
        request_ai = False
        for decision in by_index.get(index, ()):  # one bar may have multiple events
            if decision.request_ai:
                request_ai = True
                evidence.append("market_escalation")
            if decision.strategy_hint.request_ai:
                request_ai = True
                evidence.append("strategy_hint")

        candidates.append(
            HighRecallCandidate(
                index=index,
                request_ai=request_ai,
                evidence=tuple(sorted(set(evidence))),
            )
        )

    return tuple(candidates)


def high_recall_candidate_indices(
    bars: Sequence[Bar],
    *,
    timeframe: str = "15m",
    fast_period: int = 20,
    slow_period: int = 50,
) -> set[int]:
    """Return the deduplicated bar indices eligible for AI review."""
    return {
        candidate.index
        for candidate in build_high_recall_candidates(
            bars,
            timeframe=timeframe,
            fast_period=fast_period,
            slow_period=slow_period,
        )
        if candidate.request_ai
    }
