"""Deterministic research-state container for Nova.

This module stores research knowledge separately from model prose. It does not
infer whether an edge exists; it enforces that experiments, evidence, and
research decisions are represented consistently and that confirmation data is
not silently converted into development evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

DataRole = Literal["development", "confirmation", "replication"]
MechanismStatus = Literal[
    "unseen", "active", "weakened", "rejected", "candidate", "confirmed"
]


@dataclass
class EvidenceRecord:
    id: str
    experiment_id: str
    data_role: DataRole
    result: str
    uncertainty: str
    cost_assumptions: str
    interpretation: str
    limitations: str
    what_it_changes: str

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"evidence field {name} must be non-empty")
        if self.data_role not in {"development", "confirmation", "replication"}:
            raise ValueError("invalid evidence data_role")


@dataclass
class MechanismRecord:
    id: str
    statement: str
    predictions: list[str]
    status: MechanismStatus = "unseen"
    confidence: str = "unknown"
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    tested_formulations: list[str] = field(default_factory=list)
    remaining_uncertainty: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.id.strip() or not self.statement.strip():
            raise ValueError("mechanism id and statement are required")
        if not self.predictions or not all(p.strip() for p in self.predictions):
            raise ValueError("mechanism requires non-empty predictions")
        if self.status not in {
            "unseen", "active", "weakened", "rejected", "candidate", "confirmed"
        }:
            raise ValueError("invalid mechanism status")


@dataclass
class ResearchState:
    research_question: str
    asset: str
    timeframe: str
    data_boundaries: str
    mechanisms: dict[str, MechanismRecord] = field(default_factory=dict)
    evidence: dict[str, EvidenceRecord] = field(default_factory=dict)
    tested_experiments: set[str] = field(default_factory=set)
    rejected_mechanisms: set[str] = field(default_factory=set)
    prohibited_experiments: set[str] = field(default_factory=set)
    unresolved_questions: list[str] = field(default_factory=list)
    unused_research_directions: list[str] = field(default_factory=list)
    exploration_budget_remaining: int = 0
    confirmation_locked: bool = False
    confirmation_ids: set[str] = field(default_factory=set)
    current_decision: str = ""

    def validate(self) -> None:
        for name in ("research_question", "asset", "timeframe", "data_boundaries"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.exploration_budget_remaining < 0:
            raise ValueError("exploration budget cannot be negative")
        for mechanism in self.mechanisms.values():
            mechanism.validate()
        for evidence in self.evidence.values():
            evidence.validate()
            if evidence.data_role == "confirmation":
                self.confirmation_ids.add(evidence.id)
        if self.rejected_mechanisms.intersection(self.mechanisms) - {
            mid for mid, m in self.mechanisms.items() if m.status == "rejected"
        }:
            raise ValueError("rejected_mechanisms disagrees with mechanism status")

    def add_mechanism(self, mechanism: MechanismRecord) -> None:
        mechanism.validate()
        if mechanism.id in self.mechanisms:
            raise ValueError(f"mechanism already exists: {mechanism.id}")
        self.mechanisms[mechanism.id] = mechanism
        self.validate()

    def add_evidence(self, evidence: EvidenceRecord) -> None:
        evidence.validate()
        if evidence.id in self.evidence:
            raise ValueError(f"evidence already exists: {evidence.id}")
        if evidence.experiment_id in self.prohibited_experiments:
            raise ValueError("experiment is prohibited by research-state policy")
        if evidence.data_role == "confirmation" and not self.confirmation_locked:
            self.confirmation_locked = True
        if evidence.data_role == "confirmation":
            self.confirmation_ids.add(evidence.id)
        self.evidence[evidence.id] = evidence
        self.tested_experiments.add(evidence.experiment_id)
        self.validate()

    def prohibit_experiment(self, experiment_id: str) -> None:
        if not experiment_id.strip():
            raise ValueError("experiment_id is required")
        self.prohibited_experiments.add(experiment_id)

    def reject_mechanism(self, mechanism_id: str, reason: str) -> None:
        mechanism = self.mechanisms.get(mechanism_id)
        if mechanism is None:
            raise KeyError(mechanism_id)
        if not reason.strip():
            raise ValueError("rejection reason is required")
        mechanism.status = "rejected"
        mechanism.remaining_uncertainty.append(reason)
        self.rejected_mechanisms.add(mechanism_id)

    def development_available(self) -> bool:
        return self.exploration_budget_remaining > 0 and not self.confirmation_locked

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "research_question": self.research_question,
            "scope": {
                "asset": self.asset,
                "timeframe": self.timeframe,
                "data_boundaries": self.data_boundaries,
            },
            "mechanisms": {
                key: asdict(value) for key, value in self.mechanisms.items()
            },
            "evidence": {key: asdict(value) for key, value in self.evidence.items()},
            "research_space": {
                "tested_experiments": sorted(self.tested_experiments),
                "rejected_mechanisms": sorted(self.rejected_mechanisms),
                "prohibited_experiments": sorted(self.prohibited_experiments),
                "unused_research_directions": list(self.unused_research_directions),
            },
            "uncertainties": list(self.unresolved_questions),
            "current_decision": self.current_decision,
            "budget": {
                "exploration_remaining": self.exploration_budget_remaining,
            },
            "confirmation_protection": {
                "locked": self.confirmation_locked,
                "confirmation_ids": sorted(self.confirmation_ids),
            },
        }
