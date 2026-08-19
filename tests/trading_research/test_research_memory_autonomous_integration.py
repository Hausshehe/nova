from __future__ import annotations

from pathlib import Path

import pytest

from trading_research.contracts import Hypothesis
from trading_research.memory import ExperienceStore
from trading_research.researcher import DuplicateHypothesis, HypothesisProposal, Researcher


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        name="memory_gate_demo",
        thesis="A deterministic test hypothesis.",
        symbol="EURUSD",
        timeframe="D1",
        rules={"entry": "close > sma", "exit": "after 8 bars"},
        expected_edge="positive expectancy",
        falsifier="non_positive net return out of sample",
        rationale="integration test",
    )


def _record(store: ExperienceStore, dataset: Path) -> None:
    hypothesis = _hypothesis()
    store.record_experiment(
        experiment_id="existing-exp",
        created_at_utc="2026-01-01T00:00:00+00:00",
        hypothesis_name=hypothesis.name,
        symbol=hypothesis.symbol,
        timeframe=hypothesis.timeframe,
        final_decision="REJECT",
        record={
            "hypothesis": {
                "name": hypothesis.name,
                "thesis": hypothesis.thesis,
                "symbol": hypothesis.symbol,
                "timeframe": hypothesis.timeframe,
                "rules": dict(hypothesis.rules),
                "expected_edge": hypothesis.expected_edge,
                "falsifier": hypothesis.falsifier,
                "rationale": hypothesis.rationale,
            },
            "dataset": str(dataset),
            "final_decision": "REJECT",
        },
    )


def test_researcher_blocks_same_hypothesis_and_same_dataset(tmp_path: Path) -> None:
    dataset = tmp_path / "a.csv"
    dataset.write_text("dataset-a", encoding="utf-8")
    store = ExperienceStore(":memory:")
    _record(store, dataset)

    researcher = Researcher.from_memory(store)
    with pytest.raises(DuplicateHypothesis, match="DUPLICATE_EVIDENCE"):
        researcher.accept_proposal_for_dataset(
            HypothesisProposal(_hypothesis(), source="test"),
            memory=store,
            dataset=str(dataset),
        )


def test_researcher_allows_independent_dataset_validation(tmp_path: Path) -> None:
    dataset_a = tmp_path / "a.csv"
    dataset_b = tmp_path / "b.csv"
    dataset_a.write_text("dataset-a", encoding="utf-8")
    dataset_b.write_text("dataset-b", encoding="utf-8")
    store = ExperienceStore(":memory:")
    _record(store, dataset_a)

    researcher = Researcher.from_memory(store)
    fingerprint = researcher.accept_proposal_for_dataset(
        HypothesisProposal(_hypothesis(), source="test"),
        memory=store,
        dataset=str(dataset_b),
    )

    assert fingerprint
    assert researcher.accepted_count == 1


def test_researcher_fails_closed_when_current_dataset_is_missing(tmp_path: Path) -> None:
    dataset = tmp_path / "a.csv"
    dataset.write_text("dataset-a", encoding="utf-8")
    store = ExperienceStore(":memory:")
    _record(store, dataset)

    researcher = Researcher.from_memory(store)
    missing = tmp_path / "missing.csv"
    with pytest.raises(DuplicateHypothesis, match="EVIDENCE_UNAVAILABLE"):
        researcher.accept_proposal_for_dataset(
            HypothesisProposal(_hypothesis(), source="test"),
            memory=store,
            dataset=str(missing),
        )
