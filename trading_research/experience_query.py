"""Read-only queries over Nova's existing research experience memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .experience_lifecycle import ExperienceMetadata, available_at_or_before
from .experience_lifecycle_store import ExperienceLifecycleStore
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
    parent_experiment_id: str | None = None


class ExperienceQuery:
    """Read-only facade for durable research experience."""

    def __init__(
        self,
        store: ExperienceStore,
        lifecycle_store: ExperienceLifecycleStore | None = None,
    ):
        self._store = store
        self._lifecycle_store = lifecycle_store

    def history_for_hypothesis(self, hypothesis: Any) -> list[ExperienceSummary]:
        fingerprint = hypothesis_fingerprint(hypothesis)
        records = self._store.list_experiments_for_hypothesis(fingerprint)
        summaries = [self._summary_from_record(record, fingerprint) for record in records]
        if self._lifecycle_store is not None:
            lifecycle = self._lifecycle_store.list_for_hypothesis(fingerprint)
            by_id = {item.experiment_id: item for item in lifecycle}
            summaries = [self._summary_with_lifecycle(item, by_id.get(item.experiment_id)) for item in summaries]
        return summaries

    def available_history(self, hypothesis: Any, decision_time_utc: str) -> list[ExperienceSummary]:
        fingerprint = hypothesis_fingerprint(hypothesis)
        summaries = self.history_for_hypothesis(hypothesis)
        metadata = [self._metadata_from_summary(item) for item in summaries]
        return [
            self._summary_from_metadata(item)
            for item in available_at_or_before(metadata, decision_time_utc)
        ]

    def explain_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        payload = self._store.get_experiment(experiment_id)
        if payload is None:
            return None
        lifecycle = self._lifecycle_store.get(experiment_id) if self._lifecycle_store is not None else None
        return {
            "experiment_id": experiment_id,
            "final_decision": payload.get("final_decision"),
            "hypothesis": payload.get("hypothesis"),
            "dataset": payload.get("dataset"),
            "dataset_sha256": payload.get("dataset_sha256"),
            "costs": payload.get("costs"),
            "segments": payload.get("segments"),
            "knowledge_class": lifecycle.knowledge_class if lifecycle else self._knowledge_class(str(payload.get("final_decision", ""))),
            "parent_experiment_id": lifecycle.parent_experiment_id if lifecycle else None,
        }

    def prior_dispositions(self, hypothesis: Any) -> tuple[str, ...]:
        return tuple(item.final_decision for item in self.history_for_hypothesis(hypothesis))

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

    def _metadata_from_summary(self, summary: ExperienceSummary) -> ExperienceMetadata:
        return ExperienceMetadata(
            experiment_id=summary.experiment_id,
            observed_at_utc=summary.observed_at_utc,
            hypothesis_fingerprint=summary.hypothesis_fingerprint,
            dataset_sha256=summary.dataset_sha256,
            final_decision=summary.final_decision,
            knowledge_class=summary.knowledge_class,
            parent_experiment_id=summary.parent_experiment_id,
        )

    @staticmethod
    def _summary_with_lifecycle(
        summary: ExperienceSummary,
        lifecycle: ExperienceMetadata | None,
    ) -> ExperienceSummary:
        if lifecycle is None:
            return summary
        return ExperienceSummary(
            experiment_id=summary.experiment_id,
            hypothesis_fingerprint=summary.hypothesis_fingerprint,
            dataset_sha256=lifecycle.dataset_sha256,
            final_decision=lifecycle.final_decision,
            knowledge_class=lifecycle.knowledge_class,
            observed_at_utc=lifecycle.observed_at_utc,
            parent_experiment_id=lifecycle.parent_experiment_id,
        )

    @staticmethod
    def _experiment_id_from_record(record: dict[str, Any]) -> str:
        value = record.get("experiment_id")
        if isinstance(value, str) and value:
            return value
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
            parent_experiment_id=item.parent_experiment_id,
        )

    @staticmethod
    def _knowledge_class(final_decision: str) -> str:
        return {
            "REJECT": "REJECTED",
            "INCONCLUSIVE": "INCONCLUSIVE",
            "PROMISING": "HISTORICAL_RESEARCH",
        }.get(final_decision, "HISTORICAL_RESEARCH")
