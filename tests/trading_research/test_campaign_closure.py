from trading_research.research_experience_brief import ResearchExperienceBrief
from trading_research.research_planning import plan_campaign


def _brief(fingerprint: str) -> ResearchExperienceBrief:
    return ResearchExperienceBrief(
        hypothesis_fingerprint=fingerprint,
        experiment_count=1,
        dispositions=("REJECT",),
        rejected_count=1,
        inconclusive_count=0,
        historical_count=1,
        independent_validation_count=0,
        evidence_hashes=("e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e",),
        summaries=(),
    )


def test_five_frozen_hypotheses_close_same_dataset_campaign() -> None:
    briefs = tuple(_brief(str(index) * 64) for index in range(5))
    plan = plan_campaign(
        briefs,
        dataset_sha256="e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e",
        max_frozen_hypotheses=5,
    )
    assert plan.action == "CAMPAIGN_CLOSED"


def test_under_five_frozen_hypotheses_remain_bounded() -> None:
    briefs = tuple(_brief(str(index) * 64) for index in range(4))
    plan = plan_campaign(
        briefs,
        dataset_sha256="e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e",
        max_frozen_hypotheses=5,
    )
    assert plan.action == "CONTINUE_WITH_BOUNDED_NOVELTY_CHECK"
