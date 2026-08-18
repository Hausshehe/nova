import pytest

from trading_research.contracts import Hypothesis
from trading_research.researcher import (
    DuplicateHypothesis,
    HypothesisProposal,
    ResearchBudget,
    ResearchBudgetExhausted,
    Researcher,
    hypothesis_fingerprint,
)


def _hypothesis(name="h1"):
    return Hypothesis(
        name=name,
        thesis="A testable market effect exists.",
        symbol="EURUSD",
        timeframe="1D",
        rules={"entry": "rule", "exit": "exit"},
        expected_edge="Positive expectancy after costs.",
        falsifier="Non-positive out-of-sample expectancy.",
        rationale="Bounded unit test hypothesis.",
    )


def test_fingerprint_is_stable():
    assert hypothesis_fingerprint(_hypothesis()) == hypothesis_fingerprint(_hypothesis())
    assert hypothesis_fingerprint(_hypothesis("h1")) != hypothesis_fingerprint(_hypothesis("h2"))


def test_researcher_rejects_duplicate_proposals():
    researcher = Researcher(prior_fingerprints=[hypothesis_fingerprint(_hypothesis())])
    with pytest.raises(DuplicateHypothesis):
        researcher.accept_proposal(HypothesisProposal(_hypothesis(), source="test"))


def test_researcher_enforces_hypothesis_budget():
    researcher = Researcher(ResearchBudget(max_hypotheses=2, max_revisions=1))
    researcher.accept_proposal(HypothesisProposal(_hypothesis("h1"), source="test"))
    researcher.accept_proposal(HypothesisProposal(_hypothesis("h2"), source="test"))
    with pytest.raises(ResearchBudgetExhausted, match="RESEARCH_BUDGET_EXHAUSTED"):
        researcher.accept_proposal(HypothesisProposal(_hypothesis("h3"), source="test"))
    assert researcher.remaining_hypothesis_budget == 0


def test_researcher_enforces_revision_budget():
    researcher = Researcher(ResearchBudget(max_hypotheses=1, max_revisions=1))
    researcher.record_revision()
    with pytest.raises(ResearchBudgetExhausted, match="RESEARCH_BUDGET_EXHAUSTED"):
        researcher.record_revision()


def test_proposal_requires_source_and_valid_hypothesis():
    researcher = Researcher()
    with pytest.raises(ValueError, match="proposal source is required"):
        researcher.accept_proposal(HypothesisProposal(_hypothesis(), source=""))


def test_researcher_budget_can_be_reset_explicitly():
    researcher = Researcher(ResearchBudget(max_hypotheses=1, max_revisions=0))
    researcher.accept_proposal(HypothesisProposal(_hypothesis("h1"), source="test"))
    with pytest.raises(ResearchBudgetExhausted):
        researcher.accept_proposal(HypothesisProposal(_hypothesis("h2"), source="test"))
    researcher.reset_run()
    researcher.accept_proposal(HypothesisProposal(_hypothesis("h2"), source="test"))
    assert researcher.accepted_count == 1
