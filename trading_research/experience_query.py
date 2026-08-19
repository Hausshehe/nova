"""Read-only queries over Nova's existing research experience memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .experience_lifecycle import ExperienceMetadata, available_at_or_before
from .memory import ExperienceStore
from .researcher import hypothesis_fingerprint


@dataclass(frozen=True)
class ExperienceSummary:
    experiment_id: str
    hypothesis_fingerprint: str
    dataset_sha256: str | None
    final_decision: str
    knowledge_class: str
    observed_at_utc: str


class ExperienceQuery:
    """Read-only facade for durable research experience."""

    def __init__(self, store: ExperienceStore):
        self._store = store

    def history_for_hypothesis(self, hypothesis: Any) -> list[ExperienceSummary]:
        fingerprint = hypothesis_fingerprint(hypothesis)
        records = self._store.list_experiments_for_hypothesis(fingerprint)
        return [self._summary_from_record(record, fingerprint) for record in records]

    def available_history(self, hypothesis: Any, decision_time_utc: str) -> list[ExperienceSummary]:
        fingerprint = hypothesis_fingerprint(hypothesis)
        records = self._store.list_experiments_for_hypothesis(fingerprint)
        metadata = [self._metadata_from_record(record, fingerprint) for record in records]
        return [
            self._summary_from_metadata(item)
            for item in available_at_or_before(metadata, decision_time_utc)
        ]

    def explain_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        payload = self._store.get_experiment(experiment_id)
        if payload is None:
            return None
        return {
            "experiment_id": experiment_id,
            "final_decision": payload.get("final_decision"),
            "hypothesis": payload.get("hypothesis"),
            "dataset": payload.get("dataset"),
            "dataset_sha256": payload.get("dataset_sha256"),
            "costs": payload.get("costs"),
            "segments": payload.get("segments"),
            "knowledge_class": self._knowledge_class(str(payload.get("final_decision", ""))),
        }

    def prior_dispositions(self, hypothesis: Any) -> tuple[str, ...]:
        fingerprint = hypothesis_fingerprint(hypothesis)
        records = self._store.list_experiments_for_hypothesis(fingerprint)
        return tuple(str(record.get("final_decision", "")) for record in records)

    @classmethod
    def _metadata_from_record(cls, record: dict[str, Any], fingerprint: str) -> ExperienceMetadata:
        return ExperienceMetadata(
            experiment_id=cls._experiment_id_from_record(record),
            observed_at_utc=str(record.get("created_at_utc", "")),
            hypothesis_fingerprint=fingerprint,
            dataset_sha256=record.get("dataset_sha256"),
            final_decision=str(record.get("final_decision", "")),
            knowledge_class=cls._knowledge_class(str(record.get("final_decision", ""))),
        )

    @staticmethod
    def _experiment_id_from_record(record: dict[str, Any]) -> str:
        value = record.get("experiment_id")
        if isinstance(value, str) and value:
            return value
        # Older records do not embed the SQLite primary key. Preserve a stable
        # identity from the immutable evidence payload instead of inventing one.
        import hashlib
        import json
        canonical = dict(record)
        canonical.pop("created_at_utc", None)
        return hashlib.sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]

    @classmethod
    def _summary_from_record(cls, record: dict[str, Any], fingerprint: str) -> ExperienceSummary:
        return cls._summary_from_metadata(cls._metadata_from_record(record, fingerprint))

    @staticmethod
    def _summary_from_metadata(item: ExperienceMetadata) -> ExperienceSummary:
        return ExperienceSummary(
            experiment_id=item.experiment_id,
            hypothesis_fingerprint=item.hypothesis_fingerprint,
            dataset_sha256=item.dataset_sha256,
            final_decision=item.final_decision,
            knowledge_class=item.knowledge_class,
            observed_at_utc=item.observed_at_utc,
        )

    @staticmethod
    def _knowledge_class(final_decision: str) -> str:
        return {
            "REJECT": "REJECTED",
            "INCONCLUSIVE": "INCONCLUSIVE",
            "PROMISING": "HISTORICAL_RESEARCH",
        }.get(final_decision, "HISTORICAL_RESEARCH")
