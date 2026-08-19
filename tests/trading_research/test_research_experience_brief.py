from pathlib import Path

from trading_research.contracts import Hypothesis
from trading_research.experience_query import ExperienceQuery
from trading_research.memory import ExperienceStore
from trading_research.research_experience_brief import build_research_experience_brief


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        name="brief-test",
        thesis="A test hypothesis",
        symbol="EURUSD",
        timeframe="1D",
        rules={"direction": "LONG"},
        expected_edge="test edge",
        falsifier="test falsifier",
        rationale="test",
    )


def _record(path: Path, decision: str) -> dict:
    return {
        "schema_version": 1,
        "created_at_utc": "2026-01-01T00:00:00+00:00",
        "hypothesis": {
            "name": "brief-test",
            "thesis": "A test hypothesis",
            "symbol": "EURUSD",
            "timeframe": "1D",
            "rules": {"direction": "LONG"},
            "expected_edge": "test edge",
            "falsifier": "test falsifier",
            "rationale": "test",
        },
        "dataset": str(path),
        "dataset_sha256": "a" * 64,
        "total_bars": 10,
        "split_sizes": {"train": 6, "validation": 2, "test": 2},
        "costs": {"fee_bps_per_side": 1.0, "slippage_bps_per_side": 1.0},
        "segments": [],
        "final_decision": decision,
    }


def test_brief_summarizes_prior_dispositions_and_evidence(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    dataset.write_text("evidence", encoding="utf-8")
    store = ExperienceStore(":memory:")
    store.record_experiment(
        experiment_id="exp-1",
        created_at_utc="2026-01-01T00:00:00+00:00",
        hypothesis_name="brief-test",
        symbol="EURUSD",
        timeframe="1D",
        final_decision="REJECT",
        record=_record(dataset, "REJECT"),
    )
    brief = build_research_experience_brief(ExperienceQuery(store), _hypothesis())
    assert brief.experiment_count == 1
    assert brief.dispositions == ("REJECT",)
    assert brief.rejected_count == 1
    assert brief.inconclusive_count == 0
    assert brief.has_prior_evidence is True
    assert brief.has_independent_validation is False
    assert brief.evidence_hashes == ("a" * 64,)


def test_empty_brief_is_non_authoritative() -> None:
    store = ExperienceStore(":memory:")
    brief = build_research_experience_brief(ExperienceQuery(store), _hypothesis())
    assert brief.experiment_count == 0
    assert brief.has_prior_evidence is False
    assert brief.dispositions == ()
    assert brief.evidence_hashes == ()
