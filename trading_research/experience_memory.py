"""Append-only experience memory for Nova's research brain.

The memory is deliberately conservative: experiences can be appended and
queried, but never silently edited, promoted, or deleted by the memory layer.
Each record carries experiment provenance and a hash-chain link so a later
agent can distinguish historical evidence from newly generated conclusions.

This module is storage-oriented, not a trading policy. It never decides that a
strategy is safe or profitable; callers must interpret evidence through their
own deterministic research gates.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
ALLOWED_STATUSES = ("observed", "promising", "rejected", "validated", "superseded", "exploratory")


@dataclass(frozen=True)
class ExperienceRecord:
    """One immutable observation/lesson from a research experiment."""

    experiment_id: str
    hypothesis_id: str
    domain: str
    event: str
    status: str
    lesson: str
    timestamp: str
    strategy_version: str | None = None
    dataset_sha256: str | None = None
    dataset_start: str | None = None
    dataset_end: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    parent_experiment_id: str | None = None
    previous_hash: str = "GENESIS"
    record_hash: str = ""
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        experiment_id: str,
        hypothesis_id: str,
        domain: str,
        event: str,
        status: str,
        lesson: str,
        strategy_version: str | None = None,
        dataset_sha256: str | None = None,
        dataset_start: str | None = None,
        dataset_end: str | None = None,
        metrics: dict[str, Any] | None = None,
        tags: Iterable[str] = (),
        constraints: Iterable[str] = (),
        parent_experiment_id: str | None = None,
        timestamp: str | None = None,
        previous_hash: str = "GENESIS",
    ) -> "ExperienceRecord":
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"unsupported experience status: {status}")
        if not experiment_id.strip() or not hypothesis_id.strip():
            raise ValueError("experiment_id and hypothesis_id are required")
        record = cls(
            experiment_id=experiment_id,
            hypothesis_id=hypothesis_id,
            domain=domain,
            event=event,
            status=status,
            lesson=lesson,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            strategy_version=strategy_version,
            dataset_sha256=dataset_sha256,
            dataset_start=dataset_start,
            dataset_end=dataset_end,
            metrics=dict(metrics or {}),
            tags=tuple(sorted(set(tags))),
            constraints=tuple(sorted(set(constraints))),
            parent_experiment_id=parent_experiment_id,
            previous_hash=previous_hash,
        )
        return record.with_hash()

    def canonical_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("record_hash", None)
        return payload

    def with_hash(self) -> "ExperienceRecord":
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        return ExperienceRecord(**{**asdict(self), "record_hash": digest})

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> "ExperienceRecord":
        payload = json.loads(value)
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported experience schema version")
        payload["tags"] = tuple(payload.get("tags", ()))
        payload["constraints"] = tuple(payload.get("constraints", ()))
        record = cls(**payload)
        if record.status not in ALLOWED_STATUSES:
            raise ValueError(f"unsupported experience status: {record.status}")
        if record.with_hash().record_hash != record.record_hash:
            raise ValueError("experience record hash mismatch")
        return record


class ExperienceMemory:
    """Append-only JSONL memory with hash-chain validation and safe queries."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _records(self) -> list[ExperienceRecord]:
        if not self.path.exists():
            return []
        records: list[ExperienceRecord] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(ExperienceRecord.from_json(line))
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    raise ValueError(f"invalid experience memory record at line {line_number}: {exc}") from exc
        return records

    def validate_chain(self) -> None:
        previous = "GENESIS"
        for record in self._records():
            if record.previous_hash != previous:
                raise ValueError(
                    f"experience memory chain break at {record.experiment_id}: "
                    f"expected {previous}, got {record.previous_hash}"
                )
            previous = record.record_hash

    def hypothesis_seen(
        self,
        *,
        hypothesis_id: str,
        dataset_sha256: str | None,
    ) -> bool:
        return any(
            record.hypothesis_id == hypothesis_id and record.dataset_sha256 == dataset_sha256
            for record in self.all()
        )

    def assert_new_hypothesis(
        self,
        *,
        hypothesis_id: str,
        dataset_sha256: str | None,
    ) -> None:
        """Reject accidental hypothesis recycling on identical evidence."""
        if self.hypothesis_seen(hypothesis_id=hypothesis_id, dataset_sha256=dataset_sha256):
            raise ValueError(
                "hypothesis already has recorded experience for this dataset; "
                "define a genuinely new hypothesis or independent validation dataset"
            )

    def append(self, record: ExperienceRecord) -> ExperienceRecord:
        self.validate_chain()
        records = self._records()
        previous_hash = records[-1].record_hash if records else "GENESIS"
        if record.previous_hash != previous_hash:
            record = ExperienceRecord(**{**asdict(record), "previous_hash": previous_hash}).with_hash()
        elif record.record_hash != record.with_hash().record_hash:
            raise ValueError("record hash is invalid")

        existing_ids = {item.experiment_id for item in records}
        if record.experiment_id in existing_ids:
            raise ValueError(f"experiment_id already exists: {record.experiment_id}")

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.to_json() + "\n")
        return record

    def record(
        self,
        *,
        experiment_id: str,
        hypothesis_id: str,
        domain: str,
        event: str,
        status: str,
        lesson: str,
        **kwargs: Any,
    ) -> ExperienceRecord:
        records = self._records()
        previous_hash = records[-1].record_hash if records else "GENESIS"
        return self.append(
            ExperienceRecord.create(
                experiment_id=experiment_id,
                hypothesis_id=hypothesis_id,
                domain=domain,
                event=event,
                status=status,
                lesson=lesson,
                previous_hash=previous_hash,
                **kwargs,
            )
        )

    def all(self) -> tuple[ExperienceRecord, ...]:
        self.validate_chain()
        return tuple(self._records())

    def query(
        self,
        *,
        hypothesis_id: str | None = None,
        status: str | None = None,
        domain: str | None = None,
        tag: str | None = None,
    ) -> tuple[ExperienceRecord, ...]:
        records = self.all()
        return tuple(
            record
            for record in records
            if (hypothesis_id is None or record.hypothesis_id == hypothesis_id)
            and (status is None or record.status == status)
            and (domain is None or record.domain == domain)
            and (tag is None or tag in record.tags)
        )

    def lessons(self, hypothesis_id: str | None = None) -> tuple[str, ...]:
        return tuple(record.lesson for record in self.query(hypothesis_id=hypothesis_id))

    def export_json(self) -> str:
        return json.dumps(
            [asdict(record) for record in self.all()], indent=2, sort_keys=True
        )


def experience_id(*, hypothesis_id: str, dataset_sha256: str | None, experiment_name: str) -> str:
    """Build a deterministic ID so the same experiment isn't recorded twice."""
    seed = "|".join((hypothesis_id, dataset_sha256 or "NO_DATASET", experiment_name))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
