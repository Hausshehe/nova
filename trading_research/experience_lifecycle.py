"""Explicit temporal and lifecycle rules for Nova experience memory.

This module interprets existing experiment records without changing their
meaning. It prevents callers from treating later evidence as if it existed
when an earlier decision was made and provides stable knowledge classes for
research planning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

KnowledgeClass = Literal[
    "HISTORICAL_RESEARCH",
    "INDEPENDENT_VALIDATION",
    "DEMO_OBSERVATION",
    "HYPOTHESIS",
    "REJECTED",
    "INCONCLUSIVE",
    "PROMOTED",
    "RETIRED",
]


@dataclass(frozen=True)
class ExperienceMetadata:
    experiment_id: str
    observed_at_utc: str
    hypothesis_fingerprint: str
    dataset_sha256: str | None
    final_decision: str
    knowledge_class: KnowledgeClass
    parent_experiment_id: str | None = None

    def validate(self) -> None:
        if not self.experiment_id.strip():
            raise ValueError("experiment_id is required")
        datetime.fromisoformat(self.observed_at_utc)
        if not self.hypothesis_fingerprint.strip():
            raise ValueError("hypothesis_fingerprint is required")
        if self.dataset_sha256 is not None and len(self.dataset_sha256) != 64:
            raise ValueError("dataset_sha256 must be a 64-character digest")
        if self.parent_experiment_id == self.experiment_id:
            raise ValueError("experience cannot parent itself")


def available_at_or_before(
    experiences: list[ExperienceMetadata],
    decision_time_utc: str,
) -> list[ExperienceMetadata]:
    """Return only evidence that existed when a decision was made."""
    decision_time = datetime.fromisoformat(decision_time_utc)
    result: list[ExperienceMetadata] = []
    for experience in experiences:
        experience.validate()
        if datetime.fromisoformat(experience.observed_at_utc) <= decision_time:
            result.append(experience)
    return result


def validate_lineage(
    experience: ExperienceMetadata,
    known_experiment_ids: set[str],
) -> None:
    """Fail closed when a claimed parent experiment does not exist."""
    experience.validate()
    if experience.parent_experiment_id is not None and experience.parent_experiment_id not in known_experiment_ids:
        raise ValueError("parent_experiment_not_found")


def classify_research_result(final_decision: str) -> KnowledgeClass:
    """Map a deterministic research disposition to an explicit class."""
    mapping: dict[str, KnowledgeClass] = {
        "REJECT": "REJECTED",
        "INCONCLUSIVE": "INCONCLUSIVE",
        "PROMISING": "HISTORICAL_RESEARCH",
    }
    try:
        return mapping[final_decision]
    except KeyError as exc:
        raise ValueError(f"unsupported research decision: {final_decision}") from exc
