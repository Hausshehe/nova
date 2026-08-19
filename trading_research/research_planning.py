"""Bounded planning preflight over Nova's research experience.

This module does not run experiments, select strategies, alter gates, or
authorize execution. It converts durable experience into a conservative
planning recommendation that must still pass the deterministic research gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from .research_experience_brief import ResearchExperienceBrief

PlanAction = Literal[
    "NO_PRIOR_EVIDENCE",
    "REQUIRE_INDEPENDENT_EVIDENCE",
    "NO_NEW_SAME_DATASET_EVALUATION",
    "REVIEW_EXISTING_EVIDENCE",
    "RESEARCH_BUDGET_EXHAUSTED",
    "CAMPAIGN_CLOSED",
    "CONTINUE_WITH_BOUNDED_NOVELTY_CHECK",
]


@dataclass(frozen=True)
class ResearchPlan:
    action: PlanAction
    reason: str
    existing_experiment_count: int
    remaining_budget: int


def plan_from_experience(
    brief: ResearchExperienceBrief,
    *,
    dataset_sha256: str | None,
    remaining_budget: int,
) -> ResearchPlan:
    """Return the safest next planning state without performing research."""
    if remaining_budget <= 0:
        return ResearchPlan(
            action="RESEARCH_BUDGET_EXHAUSTED",
            reason="The bounded research budget is exhausted; do not generate more proposals.",
            existing_experiment_count=brief.experiment_count,
            remaining_budget=remaining_budget,
        )

    if brief.experiment_count == 0:
        return ResearchPlan(
            action="NO_PRIOR_EVIDENCE",
            reason="No prior evidence exists for this hypothesis; it still requires novelty and deterministic gate checks before testing.",
            existing_experiment_count=0,
            remaining_budget=remaining_budget,
        )

    known_hashes = set(brief.evidence_hashes)
    if dataset_sha256 and dataset_sha256 in known_hashes:
        return ResearchPlan(
            action="NO_NEW_SAME_DATASET_EVALUATION",
            reason="This dataset has already supplied evidence for the hypothesis; do not repeat same-dataset evaluation or tune around prior results.",
            existing_experiment_count=brief.experiment_count,
            remaining_budget=remaining_budget,
        )

    if brief.has_independent_validation:
        return ResearchPlan(
            action="REVIEW_EXISTING_EVIDENCE",
            reason="Independent validation already exists; review the evidence lineage and gates before proposing further work.",
            existing_experiment_count=brief.experiment_count,
            remaining_budget=remaining_budget,
        )

    return ResearchPlan(
        action="REQUIRE_INDEPENDENT_EVIDENCE",
        reason="Prior evidence exists but no independent validation is recorded; a materially new evidence source is required before reuse can be treated as independent.",
        existing_experiment_count=brief.experiment_count,
        remaining_budget=remaining_budget,
    )


def plan_campaign(
    briefs: Sequence[ResearchExperienceBrief],
    *,
    dataset_sha256: str | None,
    max_frozen_hypotheses: int = 5,
) -> ResearchPlan:
    """Apply the finite campaign ceiling before any new same-campaign proposal."""
    if max_frozen_hypotheses < 1:
        raise ValueError("max_frozen_hypotheses must be positive")

    used = len(briefs)
    if used >= max_frozen_hypotheses:
        return ResearchPlan(
            action="CAMPAIGN_CLOSED",
            reason="The finite hypothesis-family limit has been reached; require materially new evidence or a materially new market question before restarting research.",
            existing_experiment_count=sum(item.experiment_count for item in briefs),
            remaining_budget=0,
        )

    if dataset_sha256 is not None and any(dataset_sha256 in item.evidence_hashes for item in briefs):
        return ResearchPlan(
            action="NO_NEW_SAME_DATASET_EVALUATION",
            reason="This evidence source is already part of the current bounded campaign; do not repeat it outside the remaining frozen-family allowance.",
            existing_experiment_count=sum(item.experiment_count for item in briefs),
            remaining_budget=max_frozen_hypotheses - used,
        )

    return ResearchPlan(
        action="CONTINUE_WITH_BOUNDED_NOVELTY_CHECK",
        reason="The campaign remains below its frozen-family ceiling; any proposal must still pass novelty, provenance, and deterministic research gates.",
        existing_experiment_count=sum(item.experiment_count for item in briefs),
        remaining_budget=max_frozen_hypotheses - used,
    )
