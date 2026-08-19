"""Read-only queries over Nova's research experience memory.

This layer answers research-history questions without mutating memory,
running experiments, selecting strategies, or authorizing execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .experience_lifecycle import ExperienceMetadata, available_at_or_before, validate_lineage
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
    parent_experiment_id: str | None


class ExperienceQuery:
    """Read-only facade for durable research experience."""

    def __init__(self, store: ExperienceStore):
        self._store = store

    def history_for_hypothesis(self, hypothesis: Any) -> list[ExperienceSummary]:
        fingerprint = hypothesis_fingerprint(hypothesis)
        return [self._summary(item) for item in self._store.list_experience_metadata(fingerprint)]

    def available_history(self, hypothesis: Any, decision_time_utc: str) -> list[ExperienceSummary]:
        items = [
            self._metadata_from_row(row)
            for row in self._store.list_experience_metadata(hypothesis_fingerprint(hypothesis))
        ]
        return [self._summary(item) for item in available_at_or_before(items, decision_time_utc)]

    def explain_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        payload = self._store.get_experiment(experiment_id)
        if payload is None:
            return None
        metadata = self._store.get_experience_metadata(experiment_id)
        if metadata is not None:
            known = {
                row["experiment_id"]
                for row in self._store.list_experience_metadata()
            }
            self._validate_metadata(metadata, known)
        return {
            "experiment_id": experiment_id,
            "final_decision": payload.get("final_decision"),
            "hypothesis": payload.get("hypothesis"),
            "dataset": payload.get("dataset"),
            "dataset_sha256": payload.get("dataset_sha256"),
            "costs": payload.get("costs"),
            "segments": payload.get("segments"),
            "knowledge_class": metadata["knowledge_class"] if metadata else None,
            "parent_experiment_id": metadata["parent_experiment_id"] if metadata else None,
        }

    def prior_dispositions(self, hypothesis: Any) -> tuple[str, ...]:
        return tuple(item.final_decision for item in self._metadata_for_hypothesis(hypothesis))

    @staticmethod
    def _metadata_from_row(row: dict[str, Any]) -> ExperienceMetadata:
        return ExperienceMetadata(
            experiment_id=str(row["experiment_id"]),
            observed_at_utc=str(row["created_at_utc"]),
            hypothesis_fingerprint=str(row["hypothesis_fingerprint"] or ""),
            dataset_sha256=row["dataset_sha256"],
            final_decision=str(row["final_decision"]),
            knowledge_class=row["knowledge_class"],
            parent_experiment_id=row["parent_experiment_id"],
        )

    @staticmethod
    def _summary(item: ExperienceMetadata) -> ExperienceSummary:
        return ExperienceSummary(
            experiment_id=item.experiment_id,
            hypothesis_fingerprint=item.hypothesis_fingerprint,
            dataset_sha256=item.dataset_sha256,
            final_decision=item.final_decision,
            knowledge_class=item.knowledge_class,
            observed_at_utc=item.observed_at_utc,
            parent_experiment_id=item.parent_experiment_id,
        )

    def _metadata_for_hypothesis(self, hypothesis: Any) -> list[ExperienceMetadata]:
        return [
            self._metadata_from_row(row)
            for row in self._store.list_experience_metadata(hypothesis_fingerprint(hypothesis))
        ]

    @staticmethod
    def _validate_metadata(metadata: dict[str, Any], known_ids: set[str]) -> None:
        typed = ExperienceMetadata(
            experiment_id=str(metadata["experiment_id"]),
            observed_at_utc=str(metadata["created_at_utc"]),
            hypothesis_fingerprint=str(metadata["hypothesis_fingerprint"] or ""),
            dataset_sha256=metadata["dataset_sha256"],
            final_decision=str(metadata["final_decision"]),
            knowledge_class=metadata["knowledge_class"],
            parent_experiment_id=metadata["parent_experiment_id"],
        )
        validate_lineage(typed, known_ids)
