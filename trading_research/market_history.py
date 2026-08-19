"""Persistent market-history storage and compact context retrieval.

Market data is stored outside the LLM. The reasoning layer can request only the
relevant window instead of carrying the entire chart/history in every prompt.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .data import Bar


class MarketHistoryStore:
    """Small SQLite-backed OHLCV history store."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS bars (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY(symbol, timeframe, timestamp)
            )"""
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_bars_lookup ON bars(symbol, timeframe, timestamp)"
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "MarketHistoryStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def append(self, symbol: str, timeframe: str, bar: Bar) -> None:
        if not symbol.strip() or not timeframe.strip():
            raise ValueError("symbol and timeframe are required")
        bar.validate()
        timestamp = bar.timestamp.astimezone(timezone.utc).isoformat()
        self._connection.execute(
            """INSERT OR REPLACE INTO bars
               (symbol, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol.strip().upper(), timeframe.strip().upper(), timestamp,
                bar.open, bar.high, bar.low, bar.close, bar.volume,
            ),
        )
        self._connection.commit()

    def append_many(self, symbol: str, timeframe: str, bars: Sequence[Bar]) -> None:
        if not bars:
            return
        if not symbol.strip() or not timeframe.strip():
            raise ValueError("symbol and timeframe are required")
        payload = []
        for bar in bars:
            bar.validate()
            payload.append((
                symbol.strip().upper(), timeframe.strip().upper(),
                bar.timestamp.astimezone(timezone.utc).isoformat(),
                bar.open, bar.high, bar.low, bar.close, bar.volume,
            ))
        self._connection.executemany(
            """INSERT OR REPLACE INTO bars
               (symbol, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            payload,
        )
        self._connection.commit()

    def recent(self, symbol: str, timeframe: str, limit: int = 100) -> tuple[Bar, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        rows = self._connection.execute(
            """SELECT timestamp, open, high, low, close, volume
               FROM bars WHERE symbol = ? AND timeframe = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (symbol.strip().upper(), timeframe.strip().upper(), int(limit)),
        ).fetchall()
        bars = [
            Bar(
                timestamp=datetime.fromisoformat(row[0]).astimezone(timezone.utc),
                open=row[1], high=row[2], low=row[3], close=row[4], volume=row[5],
            )
            for row in reversed(rows)
        ]
        return tuple(bars)

    def between(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> tuple[Bar, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if start >= end:
            raise ValueError("start must be earlier than end")
        rows = self._connection.execute(
            """SELECT timestamp, open, high, low, close, volume
               FROM bars
               WHERE symbol = ? AND timeframe = ? AND timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp ASC LIMIT ?""",
            (
                symbol.strip().upper(), timeframe.strip().upper(),
                start.astimezone(timezone.utc).isoformat(),
                end.astimezone(timezone.utc).isoformat(),
                int(limit),
            ),
        ).fetchall()
        return tuple(
            Bar(
                timestamp=datetime.fromisoformat(row[0]).astimezone(timezone.utc),
                open=row[1], high=row[2], low=row[3], close=row[4], volume=row[5],
            )
            for row in rows
        )

    def compact_context(self, symbol: str, timeframe: str, limit: int = 100) -> str:
        """Return compact JSON context suitable for an LLM request."""
        bars = self.recent(symbol, timeframe, limit=limit)
        payload = {
            "symbol": symbol.strip().upper(),
            "timeframe": timeframe.strip().upper(),
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
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
