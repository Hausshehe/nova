"""Persistent, dependency-free research and trading experience memory.

SQLite keeps Nova's experience local and queryable without adding a service.
This layer records evidence; it does not promote strategies or authorize trades.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str
    strategy_name: str
    strategy_version: str
    symbol: str
    timeframe: str
    direction: str
    entry_price: float
    exit_price: float | None
    quantity: float
    pnl: float | None
    outcome: str
    opened_at: str
    closed_at: str | None
    market_state: dict[str, Any]
    notes: str = ""


class ExperienceStore:
    """Small SQLite store for experiments, strategy versions, and trades."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    created_at_utc TEXT NOT NULL,
                    hypothesis_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    final_decision TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS strategies (
                    strategy_name TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    hypothesis_json TEXT NOT NULL,
                    approved_at_utc TEXT,
                    notes TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (strategy_name, strategy_version)
                );

                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    strategy_name TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    quantity REAL NOT NULL,
                    pnl REAL,
                    outcome TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    market_state_json TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT ''
                );
                """
            )

    def record_experiment(
        self,
        *,
        experiment_id: str,
        created_at_utc: str,
        hypothesis_name: str,
        symbol: str,
        timeframe: str,
        final_decision: str,
        record: dict[str, Any],
    ) -> None:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO experiments
                (experiment_id, created_at_utc, hypothesis_name, symbol, timeframe,
                 final_decision, record_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    created_at_utc,
                    hypothesis_name,
                    symbol,
                    timeframe,
                    final_decision,
                    payload,
                ),
            )

    def list_experiment_hypotheses(self) -> list[dict[str, Any]]:
        """Return previously recorded hypotheses in chronological order.

        Only the stored hypothesis payload is exposed. The memory layer does
        not interpret results or promote strategies.
        """
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT record_json FROM experiments
                ORDER BY created_at_utc ASC, experiment_id ASC
                """
            ).fetchall()

        hypotheses: list[dict[str, Any]] = []
        for row in rows:
            record = json.loads(row["record_json"])
            hypothesis = record.get("hypothesis")
            if isinstance(hypothesis, dict):
                hypotheses.append(hypothesis)
        return hypotheses

    def register_strategy(
        self,
        *,
        strategy_name: str,
        strategy_version: str,
        status: str,
        hypothesis: dict[str, Any],
        approved_at_utc: str | None = None,
        notes: str = "",
    ) -> None:
        if status not in {"CANDIDATE", "APPROVED", "RETIRED", "BLOCKED"}:
            raise ValueError(f"unsupported strategy status: {status}")
        payload = json.dumps(hypothesis, ensure_ascii=False, sort_keys=True)
        with self._connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO strategies
                (strategy_name, strategy_version, status, hypothesis_json,
                 approved_at_utc, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (strategy_name, strategy_version, status, payload, approved_at_utc, notes),
            )

    def record_trade(self, trade: TradeRecord) -> None:
        if trade.direction not in {"LONG", "SHORT"}:
            raise ValueError("trade direction must be LONG or SHORT")
        if trade.quantity <= 0:
            raise ValueError("trade quantity must be positive")
        if trade.outcome not in {"OPEN", "WIN", "LOSS", "BREAKEVEN", "CANCELLED"}:
            raise ValueError(f"unsupported trade outcome: {trade.outcome}")

        with self._connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO trades
                (trade_id, strategy_name, strategy_version, symbol, timeframe,
                 direction, entry_price, exit_price, quantity, pnl, outcome,
                 opened_at, closed_at, market_state_json, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.trade_id,
                    trade.strategy_name,
                    trade.strategy_version,
                    trade.symbol,
                    trade.timeframe,
                    trade.direction,
                    trade.entry_price,
                    trade.exit_price,
                    trade.quantity,
                    trade.pnl,
                    trade.outcome,
                    trade.opened_at,
                    trade.closed_at,
                    json.dumps(trade.market_state, ensure_ascii=False, sort_keys=True),
                    trade.notes,
                ),
            )

    def list_strategy_trades(self, strategy_name: str, strategy_version: str) -> list[TradeRecord]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT * FROM trades
                WHERE strategy_name = ? AND strategy_version = ?
                ORDER BY opened_at ASC
                """,
                (strategy_name, strategy_version),
            ).fetchall()

        return [
            TradeRecord(
                trade_id=row["trade_id"],
                strategy_name=row["strategy_name"],
                strategy_version=row["strategy_version"],
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                direction=row["direction"],
                entry_price=row["entry_price"],
                exit_price=row["exit_price"],
                quantity=row["quantity"],
                pnl=row["pnl"],
                outcome=row["outcome"],
                opened_at=row["opened_at"],
                closed_at=row["closed_at"],
                market_state=json.loads(row["market_state_json"]),
                notes=row["notes"],
            )
            for row in rows
        ]

    def strategy_performance_summary(self, strategy_name: str, strategy_version: str) -> dict[str, Any]:
        trades = self.list_strategy_trades(strategy_name, strategy_version)
        closed = [trade for trade in trades if trade.outcome != "OPEN" and trade.pnl is not None]
        pnl_values = [float(trade.pnl) for trade in closed]
        wins = [value for value in pnl_values if value > 0]
        losses = [value for value in pnl_values if value < 0]
        return {
            "strategy_name": strategy_name,
            "strategy_version": strategy_version,
            "trades_total": len(trades),
            "closed_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "net_pnl": sum(pnl_values),
            "win_rate": len(wins) / len(closed) if closed else 0.0,
            "profit_factor": (
                sum(wins) / -sum(losses)
                if losses and wins
                else (float("inf") if wins else 0.0)
            ),
        }
