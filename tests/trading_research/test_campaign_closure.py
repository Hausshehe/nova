from pathlib import Path

from trading_research.autonomous_research import AutonomousResearchSession
from trading_research.campaign_closure import (
    CURRENT_EURUSD_DATASET_SHA256,
    CampaignState,
    current_eurusd_campaign_state,
    evaluate_campaign_closure,
)
from trading_research.groq_hypothesis import ResearchQuestion
from trading_research.memory import ExperienceStore
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
        evidence_hashes=(
            "e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e",
        ),
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


def test_current_eurusd_campaign_is_closed_at_five_families() -> None:
    state = current_eurusd_campaign_state()
    decision = evaluate_campaign_closure(
        state,
        dataset_sha256=CURRENT_EURUSD_DATASET_SHA256,
    )
    assert state.family_count == 5
    assert decision.action == "CAMPAIGN_CLOSED"


def test_new_evidence_source_allows_restart() -> None:
    state = CampaignState(
        dataset_sha256=CURRENT_EURUSD_DATASET_SHA256,
        completed_families=("one", "two", "three", "four", "five"),
        closed=True,
    )
    decision = evaluate_campaign_closure(
        state,
        dataset_sha256="f" * 64,
    )
    assert decision.action == "ALLOW_RESTART_NEW_EVIDENCE"


def test_new_market_question_requires_explicit_restart() -> None:
    state = current_eurusd_campaign_state()
    decision = evaluate_campaign_closure(
        state,
        dataset_sha256=CURRENT_EURUSD_DATASET_SHA256,
        market_question_changed=True,
    )
    assert decision.action == "ALLOW_RESTART_NEW_MARKET_QUESTION"


def test_new_market_question_still_requires_provenance() -> None:
    decision = evaluate_campaign_closure(
        current_eurusd_campaign_state(),
        dataset_sha256=None,
        market_question_changed=True,
    )
    assert decision.action == "EVIDENCE_FINGERPRINT_REQUIRED"


class _FailIfCalledGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, question: ResearchQuestion):
        self.calls += 1
        raise AssertionError(
            "closed campaign must block before AI proposal generation"
        )


def test_autonomous_session_blocks_before_ai_proposal(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    dataset.write_bytes(Path(__file__).read_bytes())
    generator = _FailIfCalledGenerator()
    session = AutonomousResearchSession(
        generator=generator,
        memory=ExperienceStore(":memory:"),
        signal_compiler=lambda _: None,
        campaign_state=current_eurusd_campaign_state(),
    )
    result = session.propose_and_test(
        ResearchQuestion(
            question="test question",
            symbol="EURUSD",
            timeframe="1D",
        ),
        csv_path=str(dataset),
    )
    assert result.status == "CAMPAIGN_CLOSED"
    assert generator.calls == 0


def test_autonomous_session_blocks_when_provenance_is_missing(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "dataset.csv"
    dataset.write_bytes(b"data")
    monkeypatch.setattr(autonomous_research, "_sha256_file", lambda _: None)

    generator = _FailIfCalledGenerator()
    session = AutonomousResearchSession(
        generator=generator,
        memory=ExperienceStore(":memory:"),
        signal_compiler=lambda _: None,
    )
    result = session.propose_and_test(
        ResearchQuestion(
            question="test question",
            symbol="EURUSD",
            timeframe="1D",
        ),
        csv_path=str(dataset),
    )
    assert result.status == "EVIDENCE_FINGERPRINT_REQUIRED"
    assert generator.calls == 0
