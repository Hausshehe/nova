"""Final evidence gate before a research candidate can approach MT5 work.

This gate is intentionally stricter than the first-pass backtest gate. It
requires independent validation and cost/non-overlap evidence. It does not
approve execution and does not replace human/demo authorization.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromotionEvidence:
    initial_promising: bool
    independent_validation_positive: bool
    independent_folds_positive: int
    independent_folds_total: int
    cost_survives_target_bps: bool
    non_overlapping_mean_positive: bool
    bootstrap_ci_includes_zero: bool
    reproducible: bool


@dataclass(frozen=True)
class PromotionDecision:
    eligible_for_demo_build: bool
    reasons: tuple[str, ...]


def evaluate_pre_mt5_promotion(evidence: PromotionEvidence) -> PromotionDecision:
    """Determine whether research evidence is strong enough for demo-build work.

    This is a *research readiness* decision only. It never authorizes account
    access, order placement, live trading, or automatic execution.
    """
    reasons: list[str] = []
    if not evidence.initial_promising:
        reasons.append("initial_gate_not_passed")
    if not evidence.independent_validation_positive:
        reasons.append("independent_validation_not_positive")
    if evidence.independent_folds_total <= 0:
        reasons.append("independent_fold_count_missing")
    elif evidence.independent_folds_positive * 2 <= evidence.independent_folds_total:
        reasons.append("independent_fold_consistency_insufficient")
    if not evidence.cost_survives_target_bps:
        reasons.append("cost_sensitivity_failed")
    if not evidence.non_overlapping_mean_positive:
        reasons.append("non_overlapping_result_not_positive")
    if evidence.bootstrap_ci_includes_zero:
        reasons.append("bootstrap_uncertainty_still_includes_zero")
    if not evidence.reproducible:
        reasons.append("reproducibility_requirements_failed")

    return PromotionDecision(
        eligible_for_demo_build=not reasons,
        reasons=tuple(reasons) if reasons else ("all_pre_mt5_research_requirements_passed",),
    )
