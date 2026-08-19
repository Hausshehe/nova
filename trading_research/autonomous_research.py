"""Bounded AI-assisted research proposal and experiment orchestration.

The AI is a proposal source only. Deterministic validation, novelty limits,
backtesting, gates, memory, and strategy lifecycle remain outside the model.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .campaign_closure import CampaignState, evaluate_campaign_closure
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
    payload = record.to_dict()
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


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AutonomousResearchSession:
    """A bounded session that can admit and test novel AI proposals.

    The session owns one Researcher instance, so its hypothesis and revision
    budgets cannot reset between proposals. The caller supplies a deterministic
    signal compiler; the AI never supplies executable Python or changes gates.
    Evidence reuse is controlled by durable research memory before execution.
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
        campaign_state: CampaignState | None = None,
    ) -> None:
        self.generator = generator
        self.memory = memory
        self.signal_compiler = signal_compiler
        self.gates = gates or ResearchGates()
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.strategy_version = strategy_version
        self.campaign_state = campaign_state
        self.researcher = Researcher.from_memory(memory, budget=budget)

    def propose_and_test(
        self,
        question: ResearchQuestion,
        *,
        csv_path: str,
        market_question_changed: bool = False,
    ) -> ResearchCycleResult:
        """Admit at most one proposal and immediately run its deterministic test."""
        try:
            if self.campaign_state is not None:
                closure = evaluate_campaign_closure(
                    self.campaign_state,
                    dataset_sha256=_sha256_file(csv_path),
                    market_question_changed=market_question_changed,
                )
                if closure.action == "CAMPAIGN_CLOSED":
                    return ResearchCycleResult(
                        status="CAMPAIGN_CLOSED",
                        message=closure.reason,
                    )

            proposal = self.generator.propose(question)
            fingerprint = self.researcher.accept_proposal_for_dataset(
                proposal,
                memory=self.memory,
                dataset=csv_path,
            )
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
        except DuplicateHypothesis as exc:
            message = str(exc)
            status = {
                "DUPLICATE_EVIDENCE": "DUPLICATE_EVIDENCE",
                "EVIDENCE_UNAVAILABLE": "EVIDENCE_UNAVAILABLE",
            }.get(message, "DUPLICATE_HYPOTHESIS")
            return ResearchCycleResult(
                status=status,
                message="Proposal was blocked by the deterministic research-memory gate.",
            )
        except ResearchBudgetExhausted as exc:
            return ResearchCycleResult(
                status="RESEARCH_BUDGET_EXHAUSTED",
                message=str(exc),
            )
