"""Deterministic historical replay for Nova's end-to-end demo pipeline.

Replay feeds recorded OHLCV bars through the same market monitor and demo
orchestrator used by the live architecture, while injecting deterministic
clock/state inputs. No external broker or live execution path is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .demo_orchestrator import DemoCycleResult, DemoTradingOrchestrator
from .data import Bar
from .market_monitor import MarketMonitor, MarketSnapshot


@dataclass(frozen=True)
class ReplaySummary:
    bars: int
    events: int
    ai_reviews: int
    allowed_decisions: int
    executions: int
    rejected_decisions: int
    supervisor_failures: int


class HistoricalReplay:
    """Replay ordered bars through Nova without connecting to MT5."""

    def __init__(self, monitor: MarketMonitor, orchestrator: DemoTradingOrchestrator):
        self.monitor = monitor
        self.orchestrator = orchestrator

    def run(
        self,
        symbol: str,
        timeframe: str,
        bars: Sequence[Bar],
        *,
        spread_bps: Sequence[float | None] | None = None,
    ) -> tuple[ReplaySummary, tuple[DemoCycleResult, ...]]:
        if not symbol.strip():
            raise ValueError("symbol is required")
        if not timeframe.strip():
            raise ValueError("timeframe is required")
        if not bars:
            raise ValueError("bars must not be empty")
        if spread_bps is not None and len(spread_bps) != len(bars):
            raise ValueError("spread_bps must match bars length")

        for index in range(1, len(bars)):
            if bars[index].timestamp <= bars[index - 1].timestamp:
                raise ValueError("bars must be strictly increasing by timestamp")

        results: list[DemoCycleResult] = []
        events_count = 0
        ai_reviews = 0
        allowed_decisions = 0
        executions = 0
        rejected_decisions = 0
        supervisor_failures = 0

        for index, bar in enumerate(bars):
            spread = spread_bps[index] if spread_bps is not None else None
            observed = self.monitor.observe(
                MarketSnapshot(
                    symbol=symbol,
                    timeframe=timeframe,
                    bar=bar,
                    previous_bar=bars[index - 1] if index else None,
                    spread_bps=spread,
                )
            )
            events_count += len(observed)

            for event in observed:
                cycle = self.orchestrator.process_event(
                    event,
                    broker_connected=True,
                    demo_mode=True,
                    reconciled=True,
                    market_timestamp=event.timestamp,
                    reference_time=event.timestamp,
                    price=event.price,
                )
                results.append(cycle)
                if cycle.policy_reason == "supervisor_unhealthy":
                    supervisor_failures += 1
                elif cycle.policy_reason == "no_ai_escalation":
                    pass
                elif cycle.recommendation is not None:
                    ai_reviews += 1
                    if cycle.policy_allowed:
                        allowed_decisions += 1
                    else:
                        rejected_decisions += 1
                if cycle.execution is not None and cycle.execution.accepted:
                    executions += 1

        summary = ReplaySummary(
            bars=len(bars),
            events=events_count,
            ai_reviews=ai_reviews,
            allowed_decisions=allowed_decisions,
            executions=executions,
            rejected_decisions=rejected_decisions,
            supervisor_failures=supervisor_failures,
        )
        return summary, tuple(results)
