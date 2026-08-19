from trading_research.promotion_gate import PromotionEvidence, evaluate_pre_mt5_promotion


def _strong() -> PromotionEvidence:
    return PromotionEvidence(
        initial_promising=True,
        independent_validation_positive=True,
        independent_folds_positive=3,
        independent_folds_total=4,
        cost_survives_target_bps=True,
        non_overlapping_mean_positive=True,
        bootstrap_ci_includes_zero=False,
        reproducible=True,
    )


def test_strong_evidence_is_eligible_for_demo_build() -> None:
    decision = evaluate_pre_mt5_promotion(_strong())
    assert decision.eligible_for_demo_build is True
    assert decision.reasons == ("all_pre_mt5_research_requirements_passed",)


def test_current_level_of_uncertainty_blocks_promotion() -> None:
    evidence = _strong()
    evidence = PromotionEvidence(
        **{**evidence.__dict__, "bootstrap_ci_includes_zero": True}
    )
    decision = evaluate_pre_mt5_promotion(evidence)
    assert decision.eligible_for_demo_build is False
    assert "bootstrap_uncertainty_still_includes_zero" in decision.reasons


def test_non_overlapping_failure_blocks_promotion() -> None:
    evidence = _strong()
    evidence = PromotionEvidence(
        **{**evidence.__dict__, "non_overlapping_mean_positive": False}
    )
    decision = evaluate_pre_mt5_promotion(evidence)
    assert decision.eligible_for_demo_build is False
    assert "non_overlapping_result_not_positive" in decision.reasons
