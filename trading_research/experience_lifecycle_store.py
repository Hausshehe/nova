"""Durable temporal lifecycle metadata for Nova experience records.

The existing experiment payload remains the immutable evidence record. This
companion ledger stores lifecycle metadata that can evolve independently:
knowledge class and optional parent lineage.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .experience_lifecycle import ExperienceMetadata, KnowledgeClass


class ExperienceLifecycleStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(path) == ":memory:":
            self._connection = sqlite3.connect(":memory:")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = None
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection
        return sqlite3.connect(self.path)

    def _initialize(self) -> None:
        db = self._connect()
        try:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS experience_lifecycle (
                    experiment_id TEXT PRIMARY KEY,
                    observed_at_utc TEXT NOT NULL,
                    hypothesis_fingerprint TEXT NOT NULL,
                    dataset_sha256 TEXT,
                    final_decision TEXT NOT NULL,
                    knowledge_class TEXT NOT NULL,
                    parent_experiment_id TEXT
                )
                """
            )
            db.commit()
        finally:
            if self._connection is None:
                db.close()

    def record(self, metadata: ExperienceMetadata) -> None:
        metadata.validate()
        with self._connect() as db:
            existing = db.execute(
                "SELECT observed_at_utc, hypothesis_fingerprint, dataset_sha256, final_decision, knowledge_class, parent_experiment_id FROM experience_lifecycle WHERE experiment_id = ?",
                (metadata.experiment_id,),
            ).fetchone()
            values = (
                metadata.observed_at_utc,
                metadata.hypothesis_fingerprint,
                metadata.dataset_sha256,
                metadata.final_decision,
                metadata.knowledge_class,
                metadata.parent_experiment_id,
            )
            if existing is not None:
                if tuple(existing) != values:
                    raise ValueError(
                        f"experience lifecycle already exists with different metadata: {metadata.experiment_id}"
                    )
                return
            db.execute(
                "INSERT INTO experience_lifecycle (experiment_id, observed_at_utc, hypothesis_fingerprint, dataset_sha256, final_decision, knowledge_class, parent_experiment_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (metadata.experiment_id, *values),
            )

    def get(self, experiment_id: str) -> ExperienceMetadata | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT experiment_id, observed_at_utc, hypothesis_fingerprint, dataset_sha256, final_decision, knowledge_class, parent_experiment_id FROM experience_lifecycle WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
        if row is None:
            return None
        return ExperienceMetadata(
            experiment_id=row[0],
            observed_at_utc=row[1],
            hypothesis_fingerprint=row[2],
            dataset_sha256=row[3],
            final_decision=row[4],
            knowledge_class=row[5],
            parent_experiment_id=row[6],
        )

    def list_for_hypothesis(self, hypothesis_fingerprint: str) -> list[ExperienceMetadata]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT experiment_id, observed_at_utc, hypothesis_fingerprint, dataset_sha256, final_decision, knowledge_class, parent_experiment_id FROM experience_lifecycle WHERE hypothesis_fingerprint = ? ORDER BY observed_at_utc ASC, experiment_id ASC",
                (hypothesis_fingerprint,),
            ).fetchall()
        return [
            ExperienceMetadata(
                experiment_id=row[0],
                observed_at_utc=row[1],
                hypothesis_fingerprint=row[2],
                dataset_sha256=row[3],
                final_decision=row[4],
                knowledge_class=row[5],
                parent_experiment_id=row[6],
            )
            for row in rows
        ]
