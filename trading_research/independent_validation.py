"""Explicit entry point for independent validation of an existing hypothesis.

This layer does not create or modify a strategy. It only enforces the research
memory gate before reusing a frozen hypothesis on evidence that must be new.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .contracts import Hypothesis
from .data import Bar
from .experiment import ExperimentRecord, Signal, run_experiment
from .memory import ExperienceStore
from .research_memory_gate import MemoryGateDecision, evaluate_research_memory


@dataclass(frozen=True)
class IndependentValidationResult:
    gate: MemoryGateDecision
    experiment: ExperimentRecord


def run_independent_validation(
    *,
    csv_path: str | Path,
    hypothesis: Hypothesis,
    signal: Signal,
    memory_store: ExperienceStore,
    strategy_version: str,
    fee_bps: float = 1.0,
    slippage_bps: float = 1.0,
) -> IndependentValidationResult:
    """Run a frozen hypothesis only when the evidence is genuinely new.

    A duplicate hypothesis/dataset pair is rejected before any backtest runs.
    A new dataset is explicitly classified as independent validation and then
    evaluated by the same deterministic experiment pipeline.
    """
    gate = evaluate_research_memory(
        memory_store,
        hypothesis,
        dataset=csv_path,
    )
    if not gate.allowed:
        raise ValueError(
            "Independent validation blocked: " + "; ".join(gate.reasons)
        )

    record = run_experiment(
        csv_path=str(csv_path),
        hypothesis=hypothesis,
        signal=signal,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        strategy_version=strategy_version,
        memory_store=memory_store,
    )
    return IndependentValidationResult(gate=gate, experiment=record)
