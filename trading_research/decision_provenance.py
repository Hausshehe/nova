"""Immutable provenance for Nova's trading decisions.

A decision record captures what Nova knew and why it decided something at a
specific moment. It records provenance only; it never authorizes execution.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ALLOWED_ACTIONS = {"BUY", "SELL", "HOLD", "REJECT"}
_ALLOWED_APPROVALS = {"NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TradingDecisionRecord:
    decision_id: str
    decided_at_utc: str
    strategy_name: str
    strategy_version: str
    symbol: str
    timeframe: str
    action: str
    rationale: str
    hypothesis_fingerprint: str
    dataset_sha256: str | None
    evidence_experiment_ids: tuple[str, ...]
    market_state: dict[str, Any]
    risk_snapshot: dict[str, Any]
    memory_context: dict[str, Any]
    approval_status: str = "NOT_REQUIRED"

    @property
    def memory_snapshot_hash(self) -> str:
        return _sha256_text(_canonical_json(self.memory_context))

    @property
    def record_hash(self) -> str:
        payload = {
            "decision_id": self.decision_id,
            "decided_at_utc": self.decided_at_utc,
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "action": self.action,
            "rationale": self.rationale,
            "hypothesis_fingerprint": self.hypothesis_fingerprint,
            "dataset_sha256": self.dataset_sha256,
            "evidence_experiment_ids": list(self.evidence_experiment_ids),
            "market_state": self.market_state,
            "risk_snapshot": self.risk_snapshot,
            "memory_context": self.memory_context,
            "approval_status": self.approval_status,
        }
        return _sha256_text(_canonical_json(payload))

    def validate(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("decision_id is required")
        if not self.decided_at_utc.strip():
            raise ValueError("decided_at_utc is required")
        if not self.strategy_name.strip() or not self.strategy_version.strip():
            raise ValueError("strategy identity is required")
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("symbol and timeframe are required")
        if self.action not in _ALLOWED_ACTIONS:
            raise ValueError(f"unsupported decision action: {self.action}")
        if not self.rationale.strip():
            raise ValueError("rationale is required")
        if len(self.hypothesis_fingerprint) != 64:
            raise ValueError("hypothesis_fingerprint must be a 64-character digest")
        int(self.hypothesis_fingerprint, 16)
        if self.dataset_sha256 is not None:
            if len(self.dataset_sha256) != 64:
                raise ValueError("dataset_sha256 must be a 64-character digest")
            int(self.dataset_sha256, 16)
        if self.approval_status not in _ALLOWED_APPROVALS:
            raise ValueError(f"unsupported approval status: {self.approval_status}")


class DecisionProvenanceStore:
    """SQLite store for immutable trading decision provenance."""

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
                CREATE TABLE IF NOT EXISTS decision_records (
                    decision_id TEXT PRIMARY KEY,
                    decided_at_utc TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    action TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    hypothesis_fingerprint TEXT NOT NULL,
                    dataset_sha256 TEXT,
                    evidence_experiment_ids_json TEXT NOT NULL,
                    market_state_json TEXT NOT NULL,
                    risk_snapshot_json TEXT NOT NULL,
                    memory_context_json TEXT NOT NULL,
                    memory_snapshot_hash TEXT NOT NULL,
                    approval_status TEXT NOT NULL,
                    record_hash TEXT NOT NULL
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision_strategy_time ON decision_records (strategy_name, strategy_version, decided_at_utc)"
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TradingDecisionRecord:
        record = TradingDecisionRecord(
            decision_id=row["decision_id"],
            decided_at_utc=row["decided_at_utc"],
            strategy_name=row["strategy_name"],
            strategy_version=row["strategy_version"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            action=row["action"],
            rationale=row["rationale"],
            hypothesis_fingerprint=row["hypothesis_fingerprint"],
            dataset_sha256=row["dataset_sha256"],
            evidence_experiment_ids=tuple(json.loads(row["evidence_experiment_ids_json"])),
            market_state=json.loads(row["market_state_json"]),
            risk_snapshot=json.loads(row["risk_snapshot_json"]),
            memory_context=json.loads(row["memory_context_json"]),
            approval_status=row["approval_status"],
        )
        record.validate()
        if record.memory_snapshot_hash != row["memory_snapshot_hash"]:
            raise ValueError(f"decision memory integrity failure: {record.decision_id}")
        if record.record_hash != row["record_hash"]:
            raise ValueError(f"decision provenance integrity failure: {record.decision_id}")
        return record

    def record(self, decision: TradingDecisionRecord) -> None:
        decision.validate()
        with self._connect() as db:
            existing = db.execute(
                "SELECT record_hash FROM decision_records WHERE decision_id = ?",
                (decision.decision_id,),
            ).fetchone()
            if existing is not None:
                if existing["record_hash"] == decision.record_hash:
                    return
                raise ValueError(
                    f"decision_id already exists with different provenance: {decision.decision_id}"
                )
            db.execute(
                """
                INSERT INTO decision_records
                (decision_id, decided_at_utc, strategy_name, strategy_version,
                 symbol, timeframe, action, rationale, hypothesis_fingerprint,
                 dataset_sha256, evidence_experiment_ids_json, market_state_json,
                 risk_snapshot_json, memory_context_json, memory_snapshot_hash,
                 approval_status, record_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.decided_at_utc,
                    decision.strategy_name,
                    decision.strategy_version,
                    decision.symbol,
                    decision.timeframe,
                    decision.action,
                    decision.rationale,
                    decision.hypothesis_fingerprint,
                    decision.dataset_sha256,
                    _canonical_json(list(decision.evidence_experiment_ids)),
                    _canonical_json(decision.market_state),
                    _canonical_json(decision.risk_snapshot),
                    _canonical_json(decision.memory_context),
                    decision.memory_snapshot_hash,
                    decision.approval_status,
                    decision.record_hash,
                ),
            )

    def get(self, decision_id: str) -> TradingDecisionRecord | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM decision_records WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_for_strategy(
        self,
        strategy_name: str,
        strategy_version: str,
    ) -> list[TradingDecisionRecord]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM decision_records WHERE strategy_name = ? AND strategy_version = ? ORDER BY decided_at_utc ASC, decision_id ASC",
                (strategy_name, strategy_version),
            ).fetchall()
        return [self._from_row(row) for row in rows]
