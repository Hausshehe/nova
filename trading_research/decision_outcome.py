"""Immutable links between trading decisions and their realized outcomes.

This layer records what happened after a decision. It does not alter the
original decision, authorize execution, or make a new trading decision.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ALLOWED_OUTCOMES = {"WIN", "LOSS", "BREAKEVEN", "CANCELLED"}
_ALLOWED_ATTRIBUTIONS = {"DECISION", "EXECUTION", "MARKET", "MIXED", "UNDETERMINED"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DecisionOutcomeRecord:
    outcome_id: str
    decision_id: str
    trade_id: str
    recorded_at_utc: str
    outcome: str
    realized_pnl: float
    attribution: str
    lesson: str
    execution_summary: dict[str, Any]

    @property
    def record_hash(self) -> str:
        payload = {
            "outcome_id": self.outcome_id,
            "decision_id": self.decision_id,
            "trade_id": self.trade_id,
            "recorded_at_utc": self.recorded_at_utc,
            "outcome": self.outcome,
            "realized_pnl": self.realized_pnl,
            "attribution": self.attribution,
            "lesson": self.lesson,
            "execution_summary": self.execution_summary,
        }
        return _sha256_text(_canonical_json(payload))

    def validate(self) -> None:
        for name, value in (
            ("outcome_id", self.outcome_id),
            ("decision_id", self.decision_id),
            ("trade_id", self.trade_id),
            ("recorded_at_utc", self.recorded_at_utc),
            ("lesson", self.lesson),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        if self.outcome not in _ALLOWED_OUTCOMES:
            raise ValueError(f"unsupported realized outcome: {self.outcome}")
        if self.attribution not in _ALLOWED_ATTRIBUTIONS:
            raise ValueError(f"unsupported outcome attribution: {self.attribution}")


class DecisionOutcomeStore:
    """SQLite store for immutable decision-to-trade outcome links."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    trade_id TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    realized_pnl REAL NOT NULL,
                    attribution TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    execution_summary_json TEXT NOT NULL,
                    record_hash TEXT NOT NULL
                )
                """
            )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_outcome_decision_trade ON decision_outcomes (decision_id, trade_id)"
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DecisionOutcomeRecord:
        record = DecisionOutcomeRecord(
            outcome_id=row["outcome_id"],
            decision_id=row["decision_id"],
            trade_id=row["trade_id"],
            recorded_at_utc=row["recorded_at_utc"],
            outcome=row["outcome"],
            realized_pnl=row["realized_pnl"],
            attribution=row["attribution"],
            lesson=row["lesson"],
            execution_summary=json.loads(row["execution_summary_json"]),
        )
        record.validate()
        if record.record_hash != row["record_hash"]:
            raise ValueError(f"decision outcome integrity failure: {record.outcome_id}")
        return record

    def record(self, outcome: DecisionOutcomeRecord) -> None:
        outcome.validate()
        with self._connect() as db:
            existing = db.execute(
                "SELECT record_hash FROM decision_outcomes WHERE outcome_id = ?",
                (outcome.outcome_id,),
            ).fetchone()
            if existing is not None:
                if existing["record_hash"] == outcome.record_hash:
                    return
                raise ValueError(
                    f"outcome_id already exists with different evidence: {outcome.outcome_id}"
                )
            linked = db.execute(
                "SELECT outcome_id FROM decision_outcomes WHERE decision_id = ? AND trade_id = ?",
                (outcome.decision_id, outcome.trade_id),
            ).fetchone()
            if linked is not None:
                raise ValueError("decision is already linked to this trade outcome")
            db.execute(
                """
                INSERT INTO decision_outcomes
                (outcome_id, decision_id, trade_id, recorded_at_utc, outcome,
                 realized_pnl, attribution, lesson, execution_summary_json, record_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.outcome_id,
                    outcome.decision_id,
                    outcome.trade_id,
                    outcome.recorded_at_utc,
                    outcome.outcome,
                    outcome.realized_pnl,
                    outcome.attribution,
                    outcome.lesson,
                    _canonical_json(outcome.execution_summary),
                    outcome.record_hash,
                ),
            )

    def get(self, outcome_id: str) -> DecisionOutcomeRecord | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM decision_outcomes WHERE outcome_id = ?",
                (outcome_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_for_decision(self, decision_id: str) -> list[DecisionOutcomeRecord]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM decision_outcomes WHERE decision_id = ? ORDER BY recorded_at_utc ASC, outcome_id ASC",
                (decision_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]
