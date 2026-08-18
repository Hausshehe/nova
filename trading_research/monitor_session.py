"""Long-running market observation session without an MT5 Python dependency.

The session owns timing and orchestration; a caller supplies a market-data
provider. It never places orders. AI reasoning is delegated to the adaptive
brain, which already applies escalation and cooldown rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from time import monotonic, sleep
from typing import Callable, Iterable

from .adaptive_market_brain import AdaptiveMarketBrain, AdaptiveMarketResult
from .market_monitor import MarketEvent, MarketMonitor, MarketSnapshot


@dataclass(frozen=True)
class MonitoringWindow:
    """Daily local-time window. End may be on the following calendar day."""

    start: time = time(8, 0)
    end: time = time(4, 0)

    def contains(self, current: time) -> bool:
        if self.start == self.end:
            return True
        if self.start < self.end:
            return self.start <= current < self.end
        return current >= self.start or current < self.end


@dataclass(frozen=True)
class MonitoringTick:
    timestamp: datetime
    events: tuple[MarketEvent, ...]
    results: tuple[AdaptiveMarketResult, ...]
    next_poll_seconds: int


class MarketMonitorSession:
    """Poll a supplied data source and route meaningful events to the brain."""

    def __init__(
        self,
        monitor: MarketMonitor,
        brain: AdaptiveMarketBrain,
        snapshot_provider: Callable[[], Iterable[MarketSnapshot]],
        *,
        window: MonitoringWindow | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.monitor = monitor
        self.brain = brain
        self.snapshot_provider = snapshot_provider
        self.window = window or MonitoringWindow()
        self.clock = clock or datetime.now
        self.sleeper = sleeper or sleep

    def run(self, *, max_iterations: int | None = None) -> tuple[MonitoringTick, ...]:
        """Run until stopped by the caller or an optional iteration bound.

        The default is intentionally unbounded for production monitoring. Tests
        should pass ``max_iterations`` and inject clock/sleeper dependencies.
        """
        ticks: list[MonitoringTick] = []
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            now = self.clock()
            if not self.window.contains(now.time()):
                self.sleeper(30.0)
                iterations += 1
                continue

            snapshots = tuple(self.snapshot_provider())
            events: list[MarketEvent] = []
            results: list[AdaptiveMarketResult] = []
            next_poll = 15

            for snapshot in snapshots:
                observed = self.monitor.observe(snapshot)
                events.extend(observed)
                for event in observed:
                    result = self.brain.process(event)
                    results.append(result)
                    next_poll = min(next_poll, result.escalation.recommended_poll_seconds)

            ticks.append(
                MonitoringTick(
                    timestamp=now,
                    events=tuple(events),
                    results=tuple(results),
                    next_poll_seconds=next_poll,
                )
            )
            self.sleeper(float(next_poll))
            iterations += 1

        return tuple(ticks)
