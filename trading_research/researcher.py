"""Bounded hypothesis research orchestration.

This module deliberately does not call an LLM. It defines the safe boundary
that any future Groq/local-model researcher must obey:

    proposal -> validation -> novelty check -> bounded budget -> experiment

The researcher proposes hypotheses; deterministic code remains responsible
for testing and deciding them. It never changes gates or grants execution
authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from .contracts import Hypothesis
from .memory import ExperienceStore


@dataclass(frozen=True)
class ResearchBudget:
    """Hard limits for one researcher run."""

    max_hypotheses: int = 5
    max_revisions: int = 3

    def validate(self) -> None:
        if self.max_hypotheses < 1:
            raise ValueError("max_hypotheses must be positive")
        if self.max_revisions < 0:
            raise ValueError("max_revisions cannot be negative")


@dataclass(frozen=True)
class HypothesisProposal:
    hypothesis: Hypothesis
    source: str = "unknown"
    rationale: str = ""

    def validate(self) -> None:
        self.hypothesis.validate()
        if not self.source.strip():
            raise ValueError("proposal source is required")


class ResearchBudgetExhausted(RuntimeError):
    """Raised when a bounded researcher run has no proposal budget left."""


class DuplicateHypothesis(ValueError):
    """Raised when a proposal is substantially identical to prior research."""


def hypothesis_fingerprint(hypothesis: Hypothesis) -> str:
    """Return a stable content fingerprint for a validated hypothesis."""
    hypothesis.validate()
    payload = {
        "name": hypothesis.name.strip().lower(),
        "thesis": hypothesis.thesis.strip(),
        "symbol": hypothesis.symbol.strip().upper(),
        "timeframe": hypothesis.timeframe.strip().upper(),
        "rules": dict(sorted(hypothesis.rules.items())),
        "expected_edge": hypothesis.expected_edge.strip(),
        "falsifier": hypothesis.falsifier.strip(),
        "rationale": hypothesis.rationale.strip(),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprints_from_memory(store: ExperienceStore) -> set[str]:
    """Build novelty fingerprints from hypotheses already recorded in memory.

    Malformed historical records are ignored here; they must not prevent the
    researcher from starting. New proposals still undergo strict validation.
    """
    fingerprints: set[str] = set()
    for payload in store.list_experiment_hypotheses():
        try:
            hypothesis = Hypothesis(
                name=str(payload["name"]),
                thesis=str(payload["thesis"]),
                symbol=str(payload["symbol"]),
                timeframe=str(payload["timeframe"]),
                rules=dict(payload["rules"]),
                expected_edge=str(payload["expected_edge"]),
                falsifier=str(payload["falsifier"]),
                rationale=str(payload.get("rationale", "")),
            )
            fingerprints.add(hypothesis_fingerprint(hypothesis))
        except (KeyError, TypeError, ValueError):
            continue
    return fingerprints


class Researcher:
    """Bounded proposal manager backed by previously seen fingerprints."""

    def __init__(self, budget: ResearchBudget | None = None, prior_fingerprints: Iterable[str] = ()):
        self.budget = budget or ResearchBudget()
        self.budget.validate()
        self._seen = set(prior_fingerprints)
        self._accepted = 0
        self._revisions = 0

    @classmethod
    def from_memory(cls, store: ExperienceStore, budget: ResearchBudget | None = None) -> "Researcher":
        """Create a bounded researcher whose novelty history comes from SQLite."""
        return cls(budget=budget, prior_fingerprints=fingerprints_from_memory(store))

    @property
    def accepted_count(self) -> int:
        return self._accepted

    @property
    def revision_count(self) -> int:
        return self._revisions

    @property
    def remaining_hypothesis_budget(self) -> int:
        return self.budget.max_hypotheses - self._accepted

    def accept_proposal(self, proposal: HypothesisProposal) -> str:
        """Validate and reserve one hypothesis slot without testing it."""
        proposal.validate()
        if self._accepted >= self.budget.max_hypotheses:
            raise ResearchBudgetExhausted("RESEARCH_BUDGET_EXHAUSTED")

        fingerprint = hypothesis_fingerprint(proposal.hypothesis)
        if fingerprint in self._seen:
            raise DuplicateHypothesis("DUPLICATE_HYPOTHESIS")

        self._seen.add(fingerprint)
        self._accepted += 1
        return fingerprint

    def record_revision(self) -> None:
        """Reserve one controlled revision slot for a failed experiment."""
        if self._revisions >= self.budget.max_revisions:
            raise ResearchBudgetExhausted("RESEARCH_BUDGET_EXHAUSTED")
        self._revisions += 1

    def reset_run(self, prior_fingerprints: Iterable[str] = ()) -> None:
        """Start a fresh bounded run explicitly."""
        self._seen = set(prior_fingerprints)
        self._accepted = 0
        self._revisions = 0
