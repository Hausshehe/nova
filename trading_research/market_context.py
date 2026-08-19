"""Bridge market monitoring snapshots into persistent market history."""

from __future__ import annotations

from .market_history import MarketHistoryStore
from .market_monitor import MarketSnapshot


class MarketHistoryRecorder:
    """Persist every validated monitoring snapshot for later reasoning."""

    def __init__(self, store: MarketHistoryStore):
        self.store = store

    def record(self, snapshot: MarketSnapshot) -> None:
        snapshot.validate()
        self.store.append(snapshot.symbol, snapshot.timeframe, snapshot.bar)

    def context(self, symbol: str, timeframe: str, *, limit: int = 100) -> str:
        return self.store.compact_context(symbol, timeframe, limit=limit)
