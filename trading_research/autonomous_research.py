"""Bounded AI-assisted research proposal and experiment orchestration.

The AI is a proposal source only. Deterministic validation, novelty limits,
backtesting, gates, memory, and strategy lifecycle remain outside the model.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable

from .contracts import Hypothesis, ResearchGates
from .experiment import ExperimentRecord, Signal, run_experiment
from .groq_hypothesis import GroqHypothesisGenerator, ResearchQuestion
from .memory import ExperienceStore
from .researcher import DuplicateHypothesis, ResearchBudget, ResearchBudgetExhausted, Researcher


@dataclass(frozen=True)
class ResearchCycleResult:
    status: str
    message: str
    fingerprint: str | None = None
    source: str | None = None
    experiment: ExperimentRecord | None = None


SignalCompiler = Callable[[Hypothesis], Signal]


def _experiment_id(record: ExperimentRecord) -> str:
    """Return an identity for research content, not its execution timestamp."""
    payload = record.to_dict()
    payload.pop("created_at_utc", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "exp-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _record_experience(memory: ExperienceStore, record: ExperimentRecord) -> None:
    payload = record.to_dict()
    memory.record_experiment(
        experiment_id=_experiment_id(record),
        created_at_utc=record.created_at_utc,
        hypothesis_name=record.hypothesis.name,
        symbol=record.hypothesis.symbol,
        timeframe=record.hypothesis.timeframe,
        final_decision=record.final_decision.value,
        record=payload,
    )


class AutonomousResearchSession:
    """A bounded session that can admit and test novel AI proposals.

    The session owns one Researcher instance, so its hypothesis and revision
    budgets cannot reset between proposals. The caller supplies a deterministic
    signal compiler; the AI never supplies executable Python or changes gates.
    """

    def __init__(
        self,
        *,
        generator: GroqHypothesisGenerator,
        memory: ExperienceStore,
        signal_compiler: SignalCompiler,
        budget: ResearchBudget | None = None,
        gates: ResearchGates | None = None,
        fee_bps: float = 1.0,
        slippage_bps: float = 1.0,
        strategy_version: str = "1.0",
    ) -> None:
        self.generator = generator
        self.memory = memory
        self.signal_compiler = signal_compiler
        self.gates = gates or ResearchGates()
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.strategy_version = strategy_version
        self.researcher = Researcher.from_memory(memory, budget=budget)

    def propose_and_test(self, question: ResearchQuestion, *, csv_path: str) -> ResearchCycleResult:
        """Admit at most one novel hypothesis and immediately run its deterministic test."""
        try:
            proposal = self.generator.propose(question)
            fingerprint = self.researcher.accept_proposal(proposal)
            signal = self.signal_compiler(proposal.hypothesis)
            record = run_experiment(
                csv_path=csv_path,
                hypothesis=proposal.hypothesis,
                signal=signal,
                gates=self.gates,
                fee_bps=self.fee_bps,
                slippage_bps=self.slippage_bps,
                strategy_version=self.strategy_version,
                memory_store=self.memory,
            )
            _record_experience(self.memory, record)
            return ResearchCycleResult(
                status=record.final_decision.value,
                message="Hypothesis was validated, tested, gated, and recorded.",
                fingerprint=fingerprint,
                source=proposal.source,
                experiment=record,
            )
        except DuplicateHypothesis:
            return ResearchCycleResult(
                status="DUPLICATE_HYPOTHESIS",
                message="Proposal matched prior research and was not tested.",
            )
        except ResearchBudgetExhausted as exc:
            return ResearchCycleResult(
                status="RESEARCH_BUDGET_EXHAUSTED",
                message=str(exc),
            )
