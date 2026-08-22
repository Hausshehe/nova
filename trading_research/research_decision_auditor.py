"""Deterministic auditor for Nova research decisions.

The auditor does not judge whether a market hypothesis is true. It checks whether
Nova's proposed research decision is structurally admissible: state boundaries,
mechanism diversity, experiment discrimination, budget, confirmation discipline,
and explicit falsification/stopping rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trading_research.research_state import ResearchState


@dataclass(frozen=True)
class AuditResult:
    passed: bool
    score: int
    critical_failures: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    checks: dict[str, bool] = field(default_factory=dict)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def audit_decision(decision: dict[str, Any], state: ResearchState) -> AuditResult:
    checks: dict[str, bool] = {}
    critical: list[str] = []
    warnings: list[str] = []

    mechanisms = decision.get("mechanisms", [])
    experiments = decision.get("experiment_candidates", [])
    selected_id = decision.get("selected_experiment_id")

    checks["required_core_fields"] = all(
        _text(decision.get(key))
        for key in (
            "question",
            "problem_interpretation",
            "selection_rationale",
            "falsification_rule",
            "stopping_rule",
            "confirmation_protection",
            "state_update_expectation",
        )
    )
    if not checks["required_core_fields"]:
        critical.append("missing_core_research_field")

    checks["mechanism_count"] = isinstance(mechanisms, list) and len(mechanisms) >= 2
    if not checks["mechanism_count"]:
        critical.append("fewer_than_two_mechanisms")

    mechanism_ids = {str(item.get("id")) for item in mechanisms if isinstance(item, dict)}
    mechanism_texts = {
        _text(item.get("mechanism")) for item in mechanisms if isinstance(item, dict)
    }
    checks["mechanism_ids_unique"] = len(mechanism_ids) == len(mechanisms)
    if not checks["mechanism_ids_unique"]:
        critical.append("duplicate_mechanism_ids")

    checks["mechanisms_have_predictions"] = all(
        _text(item.get("prediction")) and _text(item.get("disconfirming_observation"))
        for item in mechanisms if isinstance(item, dict)
    )
    if not checks["mechanisms_have_predictions"]:
        critical.append("mechanism_missing_prediction_or_disconfirming_observation")

    checks["mechanisms_appear_distinct"] = len(mechanism_texts) >= 2
    if not checks["mechanisms_appear_distinct"]:
        critical.append("cosmetic_mechanism_duplication")

    checks["experiment_count"] = isinstance(experiments, list) and len(experiments) >= 2
    if not checks["experiment_count"]:
        critical.append("fewer_than_two_experiment_candidates")

    experiment_ids = {str(item.get("id")) for item in experiments if isinstance(item, dict)}
    checks["experiment_ids_unique"] = len(experiment_ids) == len(experiments)
    if not checks["experiment_ids_unique"]:
        critical.append("duplicate_experiment_ids")

    checks["selected_experiment_exists"] = str(selected_id) in experiment_ids
    if not checks["selected_experiment_exists"]:
        critical.append("selected_experiment_missing")

    selected = next(
        (item for item in experiments if isinstance(item, dict) and str(item.get("id")) == str(selected_id)),
        None,
    )
    if selected is not None:
        separated = set(str(x) for x in selected.get("mechanisms_separated", []))
        checks["selected_experiment_discriminates"] = len(separated) >= 2
        if not checks["selected_experiment_discriminates"]:
            critical.append("selected_experiment_does_not_discriminate")
        elif not separated.issubset(mechanism_ids):
            critical.append("selected_experiment_separates_unknown_mechanisms")
        checks["selected_experiment_development"] = bool(selected.get("development_only", False))
        if state.confirmation_locked and checks["selected_experiment_development"]:
            critical.append("development_experiment_after_confirmation_lock")

    checks["no_repeat"] = str(selected_id) not in state.tested_experiments
    if not checks["no_repeat"]:
        critical.append("selected_experiment_already_tested")

    checks["not_prohibited"] = str(selected_id) not in state.prohibited_experiments
    if not checks["not_prohibited"]:
        critical.append("selected_experiment_prohibited")

    checks["has_falsification_rule"] = bool(_text(decision.get("falsification_rule")))
    if not checks["has_falsification_rule"]:
        critical.append("missing_falsification_rule")

    checks["has_stopping_rule"] = bool(_text(decision.get("stopping_rule")))
    if not checks["has_stopping_rule"]:
        critical.append("missing_stopping_rule")

    checks["confirmation_protection"] = bool(_text(decision.get("confirmation_protection")))
    if not checks["confirmation_protection"]:
        critical.append("missing_confirmation_protection")

    checks["all_candidates_are_development"] = all(
        bool(item.get("development_only", False)) for item in experiments if isinstance(item, dict)
    )
    if not checks["all_candidates_are_development"] and decision.get("next_action") not in {
        "CONFIRMATION_CANDIDATE",
        "STOP",
    }:
        critical.append("non_development_candidate_without_confirmation_action")

    score = round(100 * sum(checks.values()) / max(len(checks), 1))

    if decision.get("next_action") == "TEST" and state.exploration_budget_remaining <= 0:
        critical.append("test_requested_with_zero_exploration_budget")

    for experiment in experiments:
        iv = experiment.get("estimated_information_value")
        cost = experiment.get("estimated_cost")
        risk = experiment.get("overfitting_risk")
        if all(isinstance(x, (int, float)) for x in (iv, cost, risk)):
            if iv < 0.25 and cost > 0.75:
                warnings.append(f"low_information_high_cost:{experiment.get('id')}")
            if risk > 0.80:
                warnings.append(f"high_overfitting_risk:{experiment.get('id')}")

    passed = not critical
    return AuditResult(
        passed=passed,
        score=score if passed else min(score, 59),
        critical_failures=tuple(sorted(set(critical))),
        warnings=tuple(sorted(set(warnings))),
        checks=checks,
    )
