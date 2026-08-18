from trading_research.contracts import Hypothesis
from trading_research.memory import ExperienceStore
from trading_research.researcher import (
    DuplicateHypothesis,
    HypothesisProposal,
    Researcher,
)


def _hypothesis(name="baseline"):
    return Hypothesis(
        name=name,
        thesis="A testable market effect exists.",
        symbol="EURUSD",
        timeframe="1D",
        rules={"entry": "rule", "exit": "exit"},
        expected_edge="Positive expectancy after costs.",
        falsifier="Non-positive out-of-sample expectancy.",
        rationale="Memory integration test.",
    )


def test_researcher_loads_prior_hypotheses_from_memory(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    hypothesis = _hypothesis()
    store.record_experiment(
        experiment_id="001",
        created_at_utc="2026-01-01T00:00:00+00:00",
        hypothesis_name=hypothesis.name,
        symbol=hypothesis.symbol,
        timeframe=hypothesis.timeframe,
        final_decision="REJECT",
        record={"hypothesis": {
            "name": hypothesis.name,
            "thesis": hypothesis.thesis,
            "symbol": hypothesis.symbol,
            "timeframe": hypothesis.timeframe,
            "rules": dict(hypothesis.rules),
            "expected_edge": hypothesis.expected_edge,
            "falsifier": hypothesis.falsifier,
            "rationale": hypothesis.rationale,
        }},
    )

    researcher = Researcher.from_memory(store)
    try:
        researcher.accept_proposal(HypothesisProposal(hypothesis, source="test"))
    except DuplicateHypothesis:
        pass
    else:
        raise AssertionError("researcher should reject a hypothesis already in memory")


def test_researcher_from_empty_memory_accepts_new_hypothesis(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    researcher = Researcher.from_memory(store)
    fingerprint = researcher.accept_proposal(HypothesisProposal(_hypothesis(), source="test"))
    assert len(fingerprint) == 64
