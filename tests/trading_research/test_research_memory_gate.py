from pathlib import Path

from trading_research.contracts import Hypothesis
from trading_research.memory import ExperienceStore
from trading_research.research_memory_gate import evaluate_research_memory


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        name="test-hypothesis",
        thesis="A causal test hypothesis",
        symbol="EURUSD",
        timeframe="1D",
        rules={"entry": "close > prior_close"},
        expected_edge="positive net expectancy",
        falsifier="non-positive expectancy out of sample",
        rationale="test",
    )


def _record(dataset: Path, decision: str = "REJECT") -> dict:
    return {
        "hypothesis": {
            "name": "test-hypothesis",
            "thesis": "A causal test hypothesis",
            "symbol": "EURUSD",
            "timeframe": "1D",
            "rules": {"entry": "close > prior_close"},
            "expected_edge": "positive net expectancy",
            "falsifier": "non-positive expectancy out of sample",
            "rationale": "test",
        },
        "dataset": str(dataset),
        "final_decision": decision,
    }


def test_new_hypothesis_has_no_prior_evidence(tmp_path: Path) -> None:
    dataset = tmp_path / "a.csv"
    dataset.write_text("sample-a", encoding="utf-8")
    decision = evaluate_research_memory(ExperienceStore(":memory:"), _hypothesis(), dataset=dataset)
    assert decision.disposition == "NEW_HYPOTHESIS"
    assert decision.allowed is True
    assert decision.prior_experiments == 0


def test_same_hypothesis_same_dataset_is_blocked(tmp_path: Path) -> None:
    dataset = tmp_path / "a.csv"
    dataset.write_text("sample-a", encoding="utf-8")
    store = ExperienceStore(":memory:")
    store.record_experiment(
        experiment_id="exp-1",
        created_at_utc="2026-01-01T00:00:00Z",
        hypothesis_name="test-hypothesis",
        symbol="EURUSD",
        timeframe="1D",
        final_decision="REJECT",
        record=_record(dataset),
    )

    decision = evaluate_research_memory(store, _hypothesis(), dataset=dataset)
    assert decision.disposition == "DUPLICATE_EVIDENCE"
    assert decision.allowed is False
    assert decision.matching_evidence == 1


def test_same_hypothesis_new_dataset_is_independent_validation(tmp_path: Path) -> None:
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    first.write_text("sample-a", encoding="utf-8")
    second.write_text("sample-b", encoding="utf-8")
    store = ExperienceStore(":memory:")
    store.record_experiment(
        experiment_id="exp-1",
        created_at_utc="2026-01-01T00:00:00Z",
        hypothesis_name="test-hypothesis",
        symbol="EURUSD",
        timeframe="1D",
        final_decision="REJECT",
        record=_record(first),
    )

    decision = evaluate_research_memory(store, _hypothesis(), dataset=second)
    assert decision.disposition == "INDEPENDENT_VALIDATION"
    assert decision.allowed is True
    assert decision.prior_experiments == 1
    assert decision.matching_evidence == 0


def test_unavailable_prior_dataset_does_not_fake_a_match(tmp_path: Path) -> None:
    current = tmp_path / "current.csv"
    current.write_text("sample-current", encoding="utf-8")
    missing = tmp_path / "no-longer-present.csv"
    store = ExperienceStore(":memory:")
    store.record_experiment(
        experiment_id="exp-1",
        created_at_utc="2026-01-01T00:00:00Z",
        hypothesis_name="test-hypothesis",
        symbol="EURUSD",
        timeframe="1D",
        final_decision="REJECT",
        record=_record(missing),
    )

    decision = evaluate_research_memory(store, _hypothesis(), dataset=current)
    assert decision.disposition == "INDEPENDENT_VALIDATION"
    assert decision.matching_evidence == 0
