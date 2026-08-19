"""Read-only briefing of prior research experience for planning.

The briefing summarizes durable evidence. It never proposes, ranks, promotes,
or executes a strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .experience_query import ExperienceQuery, ExperienceSummary


@dataclass(frozen=True)
class ResearchExperienceBrief:
    hypothesis_fingerprint: str
    experiment_count: int
    dispositions: tuple[str, ...]
    rejected_count: int
    inconclusive_count: int
    historical_count: int
    independent_validation_count: int
    evidence_hashes: tuple[str, ...]
    summaries: tuple[ExperienceSummary, ...]

    @property
    def has_prior_evidence(self) -> bool:
        return self.experiment_count > 0

    @property
    def has_independent_validation(self) -> bool:
        return self.independent_validation_count > 0


def build_research_experience_brief(
    query: ExperienceQuery,
    hypothesis: Any,
) -> ResearchExperienceBrief:
    """Build a deterministic snapshot of known evidence for one hypothesis."""
    summaries = tuple(query.history_for_hypothesis(hypothesis))
    dispositions = tuple(item.final_decision for item in summaries)
    evidence_hashes = tuple(
        item.dataset_sha256
        for item in summaries
        if item.dataset_sha256
    )
    return ResearchExperienceBrief(
        hypothesis_fingerprint=(summaries[0].hypothesis_fingerprint if summaries else ""),
        experiment_count=len(summaries),
        dispositions=dispositions,
        rejected_count=sum(item.final_decision == "REJECT" for item in summaries),
        inconclusive_count=sum(item.final_decision == "INCONCLUSIVE" for item in summaries),
        historical_count=sum(item.knowledge_class == "HISTORICAL_RESEARCH" for item in summaries),
        independent_validation_count=sum(
            item.knowledge_class == "INDEPENDENT_VALIDATION" for item in summaries
        ),
        evidence_hashes=tuple(dict.fromkeys(evidence_hashes)),
        summaries=summaries,
    )
