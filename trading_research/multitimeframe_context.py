"""Compact multi-timeframe context retrieval for market reasoning.

The selector retrieves bounded windows from the local market-history store so an
LLM can see higher-timeframe context without receiving the entire database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .market_history import MarketHistoryStore


@dataclass(frozen=True)
class TimeframeWindow:
    timeframe: str
    limit: int

    def validate(self) -> None:
        if not self.timeframe.strip():
            raise ValueError("timeframe is required")
        if self.limit <= 0:
            raise ValueError("limit must be positive")


DEFAULT_WINDOWS = (
    TimeframeWindow("5M", 60),
    TimeframeWindow("15M", 60),
    TimeframeWindow("1H", 48),
    TimeframeWindow("4H", 42),
    TimeframeWindow("1D", 30),
)


class MultiTimeframeContext:
    """Build bounded context for one symbol from persistent market history."""

    def __init__(
        self,
        store: MarketHistoryStore,
        windows: tuple[TimeframeWindow, ...] = DEFAULT_WINDOWS,
    ) -> None:
        if not windows:
            raise ValueError("at least one timeframe window is required")
        for window in windows:
            window.validate()
        self.store = store
        self.windows = windows

    def build(self, symbol: str, *, focus_timeframe: str | None = None) -> str:
        if not symbol.strip():
            raise ValueError("symbol is required")
        selected = list(self.windows)
        if focus_timeframe:
            focus = focus_timeframe.strip().upper()
            selected.sort(key=lambda window: 0 if window.timeframe.upper() == focus else 1)

        payload = {
            "symbol": symbol.strip().upper(),
            "focus_timeframe": focus_timeframe.strip().upper() if focus_timeframe else None,
            "timeframes": [],
        }
        for window in selected:
            bars = self.store.recent(symbol, window.timeframe, limit=window.limit)
            payload["timeframes"].append(
                {
                    "timeframe": window.timeframe.upper(),
                    "bars": [
                        {
                            "timestamp": bar.timestamp.isoformat(),
                            "open": bar.open,
                            "high": bar.high,
                            "low": bar.low,
                            "close": bar.close,
                            "volume": bar.volume,
                        }
                        for bar in bars
                    ],
                }
            )
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
