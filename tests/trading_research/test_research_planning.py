from trading_research.research_experience_brief import ResearchExperienceBrief
from trading_research.research_planning import plan_from_experience


def brief(
    *,
    count: int = 0,
    dispositions: tuple[str, ...] = (),
    evidence_hashes: tuple[str, ...] = (),
    independent: int = 0,
) -> ResearchExperienceBrief:
    return ResearchExperienceBrief(
        hypothesis_fingerprint="a" * 64,
        experiment_count=count,
        dispositions=dispositions,
        rejected_count=dispositions.count("REJECT"),
        inconclusive_count=dispositions.count("INCONCLUSIVE"),
        historical_count=count,
        independent_validation_count=independent,
        evidence_hashes=evidence_hashes,
        summaries=(),
    )


def test_empty_memory_does_not_prove_anything() -> None:
    plan = plan_from_experience(brief(), dataset_sha256="a" * 64, remaining_budget=1)
    assert plan.action == "NO_PRIOR_EVIDENCE"


def test_same_dataset_is_not_retested() -> None:
    plan = plan_from_experience(
        brief(count=1, dispositions=("REJECT",), evidence_hashes=("b" * 64,)),
        dataset_sha256="b" * 64,
        remaining_budget=2,
    )
    assert plan.action == "NO_NEW_SAME_DATASET_EVALUATION"


def test_prior_evidence_requires_independent_validation() -> None:
    plan = plan_from_experience(
        brief(count=2, dispositions=("REJECT", "INCONCLUSIVE"), evidence_hashes=("b" * 64,)),
        dataset_sha256="c" * 64,
        remaining_budget=1,
    )
    assert plan.action == "REQUIRE_INDEPENDENT_EVIDENCE"


def test_existing_independent_validation_is_reviewed_not_remined() -> None:
    plan = plan_from_experience(
        brief(count=2, dispositions=("REJECT", "REJECT"), evidence_hashes=("b" * 64, "c" * 64), independent=1),
        dataset_sha256="d" * 64,
        remaining_budget=1,
    )
    assert plan.action == "REVIEW_EXISTING_EVIDENCE"


def test_exhausted_budget_stops_proposals() -> None:
    plan = plan_from_experience(brief(), dataset_sha256=None, remaining_budget=0)
    assert plan.action == "RESEARCH_BUDGET_EXHAUSTED"
