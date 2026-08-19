"""Thin integration adapter for Nova's fail-closed live-like demo pipeline.

The adapter connects validated market snapshots to history, deterministic event
 detection, adaptive reasoning, and the demo orchestrator. It never creates a
live execution gateway and never bypasses the supervisor/policy layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .demo_orchestrator import DemoCycleResult, DemoTradingOrchestrator
from .escalation import AdaptiveEscalator
from .market_history import MarketHistoryStore
from .market_monitor import MarketEvent, MarketMonitor, MarketSnapshot


@dataclass(frozen=True)
class PipelineResult:
    events: tuple[MarketEvent, ...]
    cycles: tuple[DemoCycleResult, ...]


class LiveDemoPipeline:
    """Connect market snapshots to Nova's existing demo-only decision stack."""

    def __init__(
        self,
        *,
        monitor: MarketMonitor,
        history: MarketHistoryStore,
        orchestrator: DemoTradingOrchestrator,
        broker_connected: bool = True,
        demo_mode: bool = True,
        reconciled: bool = True,
    ) -> None:
        self.monitor = monitor
        self.history = history
        self.orchestrator = orchestrator
        self.broker_connected = broker_connected
        self.demo_mode = demo_mode
        self.reconciled = reconciled

    def process_snapshot(self, snapshot: MarketSnapshot) -> PipelineResult:
        snapshot.validate()
        symbol = snapshot.symbol.strip().upper()
        timeframe = snapshot.timeframe.strip().upper()

        self.history.append(symbol, timeframe, snapshot.bar)
        events = self.monitor.observe(snapshot)
        cycles: list[DemoCycleResult] = []
        for event in events:
            cycles.append(
                self.orchestrator.process_event(
                    event,
                    broker_connected=self.broker_connected,
                    demo_mode=self.demo_mode,
                    reconciled=self.reconciled,
                    market_timestamp=event.timestamp,
                    price=event.price,
                )
            )
        return PipelineResult(tuple(events), tuple(cycles))

    def process_bar(
        self,
        *,
        symbol: str,
        timeframe: str,
        bar,
        previous_bar=None,
        spread_bps: float | None = None,
    ) -> PipelineResult:
        return self.process_snapshot(
            MarketSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                bar=bar,
                previous_bar=previous_bar,
                spread_bps=spread_bps,
            )
        )
