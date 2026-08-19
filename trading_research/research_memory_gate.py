"""Evidence-aware guard for Nova's bounded research loop.

The gate prevents the researcher from repeatedly spending compute on the same
hypothesis/evidence pair while still permitting deliberate validation on an
independent dataset. It never decides that a strategy is profitable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .contracts import Hypothesis
from .evidence_identity import same_evidence, sha256_file
from .memory import ExperienceStore
from .researcher import hypothesis_fingerprint


Disposition = Literal[
    "NEW_HYPOTHESIS",
    "DUPLICATE_EVIDENCE",
    "INDEPENDENT_VALIDATION",
    "EVIDENCE_UNAVAILABLE",
]


@dataclass(frozen=True)
class MemoryGateDecision:
    disposition: Disposition
    hypothesis_fingerprint: str
    dataset_sha256: str | None
    prior_experiments: int
    matching_evidence: int
    prior_decisions: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return self.disposition in {"NEW_HYPOTHESIS", "INDEPENDENT_VALIDATION"}


def dataset_sha256(path: str | Path) -> str | None:
    return sha256_file(path)


def evaluate_research_memory(
    store: ExperienceStore,
    hypothesis: Hypothesis,
    *,
    dataset: str | Path | None,
) -> MemoryGateDecision:
    """Classify a proposal against durable experiment memory.

    A known hypothesis is not automatically rejected: a genuinely independent
    dataset is a valid validation experiment. Reusing the same evidence is
    blocked so that repeated tuning cannot turn the test set into training data.
    Stored dataset fingerprints are authoritative; historical file paths are not
    consulted when deciding whether prior evidence matches.
    """
    hypothesis.validate()
    fingerprint = hypothesis_fingerprint(hypothesis)
    evidence_hash = dataset_sha256(dataset) if dataset is not None else None
    prior = store.list_experiments_for_hypothesis(fingerprint)

    prior_decisions = tuple(str(item.get("final_decision", "")) for item in prior)

    if prior and evidence_hash is None:
        return MemoryGateDecision(
            disposition="EVIDENCE_UNAVAILABLE",
            hypothesis_fingerprint=fingerprint,
            dataset_sha256=None,
            prior_experiments=len(prior),
            matching_evidence=0,
            prior_decisions=prior_decisions,
            reasons=(
                "current_dataset_evidence_unavailable",
                "fail_closed_instead_of_assuming_independent_validation",
            ),
        )

    matches = sum(
        1 for item in prior if same_evidence(item, evidence_hash)
    )

    if matches:
        return MemoryGateDecision(
            disposition="DUPLICATE_EVIDENCE",
            hypothesis_fingerprint=fingerprint,
            dataset_sha256=evidence_hash,
            prior_experiments=len(prior),
            matching_evidence=matches,
            prior_decisions=prior_decisions,
            reasons=(
                "same_hypothesis_and_same_dataset_already_evaluated",
                "do_not_retune_against_existing_evidence",
            ),
        )

    if prior:
        return MemoryGateDecision(
            disposition="INDEPENDENT_VALIDATION",
            hypothesis_fingerprint=fingerprint,
            dataset_sha256=evidence_hash,
            prior_experiments=len(prior),
            matching_evidence=0,
            prior_decisions=prior_decisions,
            reasons=(
                "hypothesis_has_prior_evidence",
                "new_dataset_may_be_used_for_independent_validation",
            ),
        )

    return MemoryGateDecision(
        disposition="NEW_HYPOTHESIS",
        hypothesis_fingerprint=fingerprint,
        dataset_sha256=evidence_hash,
        prior_experiments=0,
        matching_evidence=0,
        prior_decisions=(),
        reasons=("no_prior_evidence_found",),
    )
