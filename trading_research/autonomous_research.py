"""One bounded AI-assisted research cycle.

The cycle is intentionally narrow:

research question -> AI proposal -> strict validation -> novelty/budget gate

The module does not run backtests or grant execution authority. A caller must
pass the accepted proposal to the deterministic experiment runner.
"""

from __future__ import annotations

from dataclasses import dataclass

from .groq_hypothesis import GroqHypothesisGenerator, ResearchQuestion
from .memory import ExperienceStore
from .researcher import DuplicateHypothesis, ResearchBudget, Researcher


@dataclass(frozen=True)
class ResearchCycleResult:
    status: str
    message: str
    fingerprint: str | None = None
    source: str | None = None


def run_proposal_cycle(
    question: ResearchQuestion,
    *,
    generator: GroqHypothesisGenerator,
    memory: ExperienceStore,
    budget: ResearchBudget | None = None,
) -> ResearchCycleResult:
    """Generate and reserve at most one novel hypothesis for this cycle."""
    researcher = Researcher.from_memory(memory, budget=budget)
    try:
        proposal = generator.propose(question)
        fingerprint = researcher.accept_proposal(proposal)
    except DuplicateHypothesis:
        return ResearchCycleResult(
            status="DUPLICATE_HYPOTHESIS",
            message="Proposal matched prior research and was not admitted.",
        )
    return ResearchCycleResult(
        status="PROPOSAL_ACCEPTED",
        message="Novel hypothesis admitted to the bounded research queue.",
        fingerprint=fingerprint,
        source=proposal.source,
    )
