"""Continuous, dependency-free market observation and event detection.

The monitor consumes validated OHLCV snapshots from any market-data source.
It never calls an LLM and never executes trades. Its job is to turn a stream
of ordinary market updates into a small number of meaningful events that a
future AI reasoning layer may inspect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .data import Bar


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    timeframe: str
    bar: Bar
    previous_bar: Bar | None = None
    spread_bps: float | None = None

    def validate(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if not self.timeframe.strip():
            raise ValueError("timeframe is required")
        if self.spread_bps is not None and self.spread_bps < 0:
            raise ValueError("spread_bps cannot be negative")


@dataclass(frozen=True)
class MarketEvent:
    event_type: str
    symbol: str
    timeframe: str
    timestamp: datetime
    reason: str
    price: float
    change_bps: float | None = None
    spread_bps: float | None = None


@dataclass(frozen=True)
class EventThresholds:
    """Cheap deterministic thresholds for escalating market observations."""

    price_move_bps: float = 20.0
    spread_change_bps: float = 10.0
    require_new_bar: bool = True

    def validate(self) -> None:
        if self.price_move_bps <= 0:
            raise ValueError("price_move_bps must be positive")
        if self.spread_change_bps <= 0:
            raise ValueError("spread_change_bps must be positive")


class MarketMonitor:
    """Stateful event detector for an arbitrarily long monitoring session."""

    def __init__(self, thresholds: EventThresholds | None = None):
        self.thresholds = thresholds or EventThresholds()
        self.thresholds.validate()
        self._last_timestamp: dict[tuple[str, str], datetime] = {}
        self._last_price: dict[tuple[str, str], float] = {}
        self._last_spread: dict[tuple[str, str], float] = {}

    def observe(self, snapshot: MarketSnapshot) -> tuple[MarketEvent, ...]:
        snapshot.validate()
        key = (snapshot.symbol.strip().upper(), snapshot.timeframe.strip().upper())
        previous_timestamp = self._last_timestamp.get(key)
        previous_price = self._last_price.get(key)
        previous_spread = self._last_spread.get(key)

        events: list[MarketEvent] = []
        new_bar = previous_timestamp is None or snapshot.bar.timestamp > previous_timestamp

        if self.thresholds.require_new_bar and not new_bar:
            return tuple()

        price = snapshot.bar.close
        change_bps = None
        if previous_price is not None and previous_price > 0:
            change_bps = abs(price / previous_price - 1.0) * 10_000.0
            if change_bps >= self.thresholds.price_move_bps:
                events.append(
                    MarketEvent(
                        event_type="PRICE_MOVE",
                        symbol=key[0],
                        timeframe=key[1],
                        timestamp=snapshot.bar.timestamp,
                        reason=f"close moved {change_bps:.2f} bps since last observed bar",
                        price=price,
                        change_bps=change_bps,
                        spread_bps=snapshot.spread_bps,
                    )
                )

        if snapshot.spread_bps is not None and previous_spread is not None:
            spread_change = abs(snapshot.spread_bps - previous_spread)
            if spread_change >= self.thresholds.spread_change_bps:
                events.append(
                    MarketEvent(
                        event_type="SPREAD_CHANGE",
                        symbol=key[0],
                        timeframe=key[1],
                        timestamp=snapshot.bar.timestamp,
                        reason=f"spread changed {spread_change:.2f} bps",
                        price=price,
                        spread_bps=snapshot.spread_bps,
                    )
                )

        if new_bar:
            events.append(
                MarketEvent(
                    event_type="NEW_BAR",
                    symbol=key[0],
                    timeframe=key[1],
                    timestamp=snapshot.bar.timestamp,
                    reason="new bar observed",
                    price=price,
                    change_bps=change_bps,
                    spread_bps=snapshot.spread_bps,
                )
            )

        self._last_timestamp[key] = snapshot.bar.timestamp
        self._last_price[key] = price
        if snapshot.spread_bps is not None:
            self._last_spread[key] = snapshot.spread_bps
        return tuple(events)

    def observe_history(
        self,
        symbol: str,
        timeframe: str,
        bars: Sequence[Bar],
        *,
        spreads_bps: Sequence[float | None] | None = None,
    ) -> tuple[MarketEvent, ...]:
        """Replay ordered bars through the monitor for deterministic testing."""
        if not bars:
            raise ValueError("bars must not be empty")
        if spreads_bps is not None and len(spreads_bps) != len(bars):
            raise ValueError("spreads_bps must match bars length")
        events: list[MarketEvent] = []
        for index, bar in enumerate(bars):
            previous = bars[index - 1] if index else None
            spread = spreads_bps[index] if spreads_bps is not None else None
            events.extend(
                self.observe(
                    MarketSnapshot(
                        symbol=symbol,
                        timeframe=timeframe,
                        bar=bar,
                        previous_bar=previous,
                        spread_bps=spread,
                    )
                )
            )
        return tuple(events)
