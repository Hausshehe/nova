"""Explicit entry point for independent validation of an existing hypothesis.

This layer does not create or modify a strategy. It only enforces the research
memory gate before reusing a frozen hypothesis on evidence that must be new.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .contracts import Hypothesis
from .experiment import ExperimentRecord, Signal, run_experiment
from .experience_lifecycle import ExperienceMetadata
from .experience_lifecycle_store import ExperienceLifecycleStore
from .memory import ExperienceStore
from .research_memory_gate import MemoryGateDecision, evaluate_research_memory
from .researcher import hypothesis_fingerprint


@dataclass(frozen=True)
class IndependentValidationResult:
    gate: MemoryGateDecision
    experiment: ExperimentRecord


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_independent_validation(
    *,
    csv_path: str | Path,
    hypothesis: Hypothesis,
    signal: Signal,
    memory_store: ExperienceStore,
    strategy_version: str,
    fee_bps: float = 1.0,
    slippage_bps: float = 1.0,
    lifecycle_store: ExperienceLifecycleStore | None = None,
) -> IndependentValidationResult:
    """Run a frozen hypothesis only when the evidence is genuinely new.

    A duplicate hypothesis/dataset pair is rejected before any backtest runs.
    A new dataset is explicitly classified as independent validation and its
    lifecycle metadata is persisted when a lifecycle store is supplied.
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

    prior = memory_store.list_experiments_for_hypothesis(gate.hypothesis_fingerprint)
    parent_experiment_id = prior[-1].get("experiment_id") if prior else None

    record = run_experiment(
        csv_path=str(csv_path),
        hypothesis=hypothesis,
        signal=signal,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        strategy_version=strategy_version,
        memory_store=memory_store,
    )

    active_lifecycle = lifecycle_store
    if active_lifecycle is None and str(memory_store.path) != ":memory:":
        active_lifecycle = ExperienceLifecycleStore(memory_store.path)

    if active_lifecycle is not None:
        matches = [
            item
            for item in memory_store.list_experiments_for_hypothesis(
                hypothesis_fingerprint(hypothesis)
            )
            if item.get("created_at_utc") == record.created_at_utc
            and item.get("dataset_sha256") == _sha256(csv_path)
        ]
        if len(matches) != 1:
            raise ValueError("independent_validation_experiment_identity_ambiguous")
        experiment_id = str(matches[0]["experiment_id"])
        active_lifecycle.record(
            ExperienceMetadata(
                experiment_id=experiment_id,
                observed_at_utc=record.created_at_utc,
                hypothesis_fingerprint=gate.hypothesis_fingerprint,
                dataset_sha256=record.dataset_sha256,
                final_decision=record.final_decision.value,
                knowledge_class="INDEPENDENT_VALIDATION",
                parent_experiment_id=parent_experiment_id,
            )
        )

    return IndependentValidationResult(gate=gate, experiment=record)
