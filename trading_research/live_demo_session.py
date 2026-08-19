"""Bounded live-like demo session loop with deterministic scheduling.

This runner owns timing and session hours, but deliberately does not fetch market
data, call an LLM, or place live orders itself. A caller supplies one snapshot
provider and one event processor. The supplied processor is expected to remain
demo-only (for example DemoTradingOrchestrator).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Any


@dataclass(frozen=True)
class DemoSessionConfig:
    start: time = time(8, 0)
    end: time = time(16, 0)
    poll_interval: timedelta = timedelta(seconds=15)

    def validate(self) -> None:
        if self.start >= self.end:
            raise ValueError("session start must be before session end")
        if self.poll_interval.total_seconds() <= 0:
            raise ValueError("poll_interval must be positive")


@dataclass(frozen=True)
class DemoSessionStats:
    polls: int
    processed_events: int
    started_at: datetime
    stopped_at: datetime
    stop_reason: str


class LiveDemoSession:
    """Run a bounded demo session without owning any trading authority."""

    def __init__(
        self,
        *,
        config: DemoSessionConfig | None = None,
        snapshot_provider: Callable[[], Any] | None = None,
        event_processor: Callable[[Any], Any] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        import time as _time
        self.config = config or DemoSessionConfig()
        self.config.validate()
        self.snapshot_provider = snapshot_provider
        self.event_processor = event_processor
        self.sleep = sleep or _time.sleep

    def _in_window(self, now: datetime) -> bool:
        local = now.astimezone().time().replace(tzinfo=None)
        return self.config.start <= local < self.config.end

    def run(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        max_polls: int | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> DemoSessionStats:
        """Run until session end, stop request, or max_polls.

        A missing provider/processor is intentionally a no-op session; this lets
        scheduling be tested without accidentally creating a trading path.
        """
        clock = now or (lambda: datetime.now(timezone.utc))
        requested = stop_requested or (lambda: False)
        started = clock()
        polls = 0
        processed = 0
        reason = "session_end"

        while self._in_window(clock()):
            if requested():
                reason = "stop_requested"
                break
            if max_polls is not None and polls >= max_polls:
                reason = "max_polls"
                break
            polls += 1
            if self.snapshot_provider is not None and self.event_processor is not None:
                snapshot = self.snapshot_provider()
                result = self.event_processor(snapshot)
                if result is not None:
                    processed += 1
            if max_polls is not None and polls >= max_polls:
                reason = "max_polls"
                break
            self.sleep(self.config.poll_interval.total_seconds())

        stopped = clock()
        return DemoSessionStats(polls, processed, started, stopped, reason)
