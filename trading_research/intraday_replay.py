"""Intraday replay scheduler for validating Nova's monitoring cadence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable


@dataclass(frozen=True)
class ReplayObservation:
    timestamp: datetime
    price: float


@dataclass(frozen=True)
class ReplayStats:
    observations: int
    review_slots: int
    elapsed_seconds: float


def run_intraday_schedule(
    observations: Iterable[ReplayObservation],
    *,
    poll_seconds: int = 15,
    start: datetime | None = None,
    end: datetime | None = None,
) -> ReplayStats:
    """Count fixed-cadence observation slots without wall-clock sleeping."""
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")
    rows = tuple(observations)
    if not rows:
        return ReplayStats(0, 0, 0.0)
    if any(row.timestamp.tzinfo is None for row in rows):
        raise ValueError("observation timestamps must be timezone-aware")
    ordered = tuple(sorted(rows, key=lambda row: row.timestamp))
    window_start = start or ordered[0].timestamp
    window_end = end or ordered[-1].timestamp
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise ValueError("start/end must be timezone-aware")
    if window_start > window_end:
        raise ValueError("start must not be after end")
    elapsed = max(0.0, (window_end - window_start).total_seconds())
    slots = int(elapsed // poll_seconds) + 1
    observations_in_window = sum(window_start <= row.timestamp <= window_end for row in ordered)
    return ReplayStats(observations_in_window, slots, elapsed)
