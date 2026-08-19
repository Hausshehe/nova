"""Persistent, dependency-free research and trading experience memory.

SQLite keeps Nova's experience local and queryable without adding a service.
This layer records evidence; it does not promote strategies or authorize trades.
Research experiments are immutable once recorded; trade rows remain updateable
because an OPEN trade legitimately transitions to a closed outcome.
"""

from __future__ import annotations

import hashlib
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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint_hypothesis(hypothesis: dict[str, Any]) -> str:
    canonical = _canonical_json(hypothesis)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _file_sha256(path: str | Path) -> str | None:
    candidate = Path(path)
    if not candidate.is_file():
        return None
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _evidence_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Exclude runtime creation time from experiment evidence identity."""
    payload = dict(record)
    payload.pop("created_at_utc", None)
    return payload


class ExperienceStore:
    """SQLite store for experiments, strategy versions, and trades."""

    def __init__(self, path: str | Path):
        self._shared_memory_uri: str | None = None
        self._keeper: sqlite3.Connection | None = None
        if str(path) == ":memory:":
            self.path = Path(":memory:")
            self._shared_memory_uri = f"file:nova_experience_{id(self)}?mode=memory&cache=shared"
            self._keeper = sqlite3.connect(self._shared_memory_uri, uri=True)
            self._keeper.row_factory = sqlite3.Row
            self._initialize(self._keeper)
        else:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._shared_memory_uri is not None:
            connection = sqlite3.connect(self._shared_memory_uri, uri=True)
        else:
            connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _initialize(self, db: sqlite3.Connection | None = None) -> None:
        owns_connection = db is None
        connection = db or self._connect()
        try:
            connection.executescript(
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
            self._ensure_column(connection, "experiments", "dataset_sha256", "TEXT")
            self._ensure_column(connection, "experiments", "hypothesis_fingerprint", "TEXT")
            self._ensure_column(connection, "experiments", "record_hash", "TEXT")

            rows = connection.execute(
                "SELECT experiment_id, record_json, record_hash FROM experiments ORDER BY created_at_utc ASC, experiment_id ASC"
            ).fetchall()
            for row in rows:
                if row["record_hash"]:
                    continue
                payload = json.loads(row["record_json"])
                connection.execute(
                    "UPDATE experiments SET record_hash = ? WHERE experiment_id = ?",
                    (self._experiment_hash(payload), row["experiment_id"]),
                )
            connection.commit()
        finally:
            if owns_connection:
                connection.close()

    @staticmethod
    def _experiment_hash(record: dict[str, Any]) -> str:
        return hashlib.sha256(_canonical_json(_evidence_payload(record)).encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_experiment_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["record_json"])
        expected = ExperienceStore._experiment_hash(payload)
        if row["record_hash"] and row["record_hash"] != expected:
            raise ValueError(f"experiment memory integrity failure: {row['experiment_id']}")
        return payload

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
        if not experiment_id.strip():
            raise ValueError("experiment_id is required")
        payload = _canonical_json(record)
        record_hash = self._experiment_hash(record)
        hypothesis = record.get("hypothesis")
        hypothesis_fingerprint = (
            _fingerprint_hypothesis(hypothesis) if isinstance(hypothesis, dict) else None
        )
        dataset_sha256 = _file_sha256(record.get("dataset", ""))

        with self._connect() as db:
            existing = db.execute(
                "SELECT record_hash FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            if existing is not None:
                if existing["record_hash"] == record_hash:
                    return
                raise ValueError(f"experiment_id already exists with different evidence: {experiment_id}")

            db.execute(
                """
                INSERT INTO experiments
                (experiment_id, created_at_utc, hypothesis_name, symbol, timeframe,
                 final_decision, record_json, dataset_sha256, hypothesis_fingerprint, record_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    created_at_utc,
                    hypothesis_name,
                    symbol,
                    timeframe,
                    final_decision,
                    payload,
                    dataset_sha256,
                    hypothesis_fingerprint,
                    record_hash,
                ),
            )

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
        if row is None:
            return None
        return self._validate_experiment_row(row)

    def list_experiment_hypotheses(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT experiment_id, record_json, record_hash FROM experiments ORDER BY created_at_utc ASC, experiment_id ASC"
            ).fetchall()
        hypotheses: list[dict[str, Any]] = []
        for row in rows:
            record = self._validate_experiment_row(row)
            hypothesis = record.get("hypothesis")
            if isinstance(hypothesis, dict):
                hypotheses.append(hypothesis)
        return hypotheses

    def list_experiments_for_hypothesis(self, hypothesis_fingerprint: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT experiment_id, record_json, record_hash
                FROM experiments
                WHERE hypothesis_fingerprint = ?
                ORDER BY created_at_utc ASC, experiment_id ASC
                """,
                (hypothesis_fingerprint,),
            ).fetchall()
        return [self._validate_experiment_row(row) for row in rows]

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

    def get_strategy(self, strategy_name: str, strategy_version: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT strategy_name, strategy_version, status, hypothesis_json,
                       approved_at_utc, notes
                FROM strategies
                WHERE strategy_name = ? AND strategy_version = ?
                """,
                (strategy_name, strategy_version),
            ).fetchone()
        if row is None:
            return None
        return {
            "strategy_name": row["strategy_name"],
            "strategy_version": row["strategy_version"],
            "status": row["status"],
            "hypothesis": json.loads(row["hypothesis_json"]),
            "approved_at_utc": row["approved_at_utc"],
            "notes": row["notes"],
        }

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
