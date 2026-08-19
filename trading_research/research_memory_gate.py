"""Evidence-aware guard for Nova's bounded research loop.

The gate prevents the researcher from repeatedly spending compute on the same
hypothesis/evidence pair while still permitting deliberate validation on an
independent dataset. It never decides that a strategy is profitable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .contracts import Hypothesis
from .memory import ExperienceStore
from .researcher import hypothesis_fingerprint


Disposition = Literal[
    "NEW_HYPOTHESIS",
    "DUPLICATE_EVIDENCE",
    "INDEPENDENT_VALIDATION",
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
        return self.disposition != "DUPLICATE_EVIDENCE"


def dataset_sha256(path: str | Path) -> str | None:
    candidate = Path(path)
    if not candidate.is_file():
        return None
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    """
    hypothesis.validate()
    fingerprint = hypothesis_fingerprint(hypothesis)
    evidence_hash = dataset_sha256(dataset) if dataset is not None else None
    prior = store.list_experiments_for_hypothesis(fingerprint)

    prior_decisions = tuple(str(item.get("final_decision", "")) for item in prior)
    matches = 0
    for item in prior:
        old_path = item.get("dataset")
        old_hash = dataset_sha256(old_path) if old_path else None
        if evidence_hash is not None and old_hash is not None and old_hash == evidence_hash:
            matches += 1

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
