from pathlib import Path

import pytest

import trading_research.independent_validation as module
from trading_research.contracts import Hypothesis
from trading_research.experiment import ExperimentRecord
from trading_research.memory import ExperienceStore


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        name="validation-hypothesis",
        thesis="A causal validation hypothesis",
        symbol="EURUSD",
        timeframe="1D",
        rules={"entry": "close > prior_close"},
        expected_edge="positive net expectancy",
        falsifier="negative unseen expectancy",
        rationale="test",
    )


def _record(dataset: Path) -> dict:
    return {
        "hypothesis": {
            "name": "validation-hypothesis",
            "thesis": "A causal validation hypothesis",
            "symbol": "EURUSD",
            "timeframe": "1D",
            "rules": {"entry": "close > prior_close"},
            "expected_edge": "positive net expectancy",
            "falsifier": "negative unseen expectancy",
            "rationale": "test",
        },
        "dataset": str(dataset),
        "final_decision": "REJECT",
    }


def test_duplicate_validation_is_blocked_before_backtest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = tmp_path / "sample.csv"
    dataset.write_text("same", encoding="utf-8")
    store = ExperienceStore(":memory:")
    store.record_experiment(
        experiment_id="prior",
        created_at_utc="2026-01-01T00:00:00Z",
        hypothesis_name="validation-hypothesis",
        symbol="EURUSD",
        timeframe="1D",
        final_decision="REJECT",
        record=_record(dataset),
    )

    called = False

    def should_not_run(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("backtest must not run for duplicate evidence")

    monkeypatch.setattr(module, "run_experiment", should_not_run)

    with pytest.raises(ValueError, match="Independent validation blocked"):
        module.run_independent_validation(
            csv_path=dataset,
            hypothesis=_hypothesis(),
            signal=lambda bars, index: False,
            memory_store=store,
            strategy_version="v1",
        )

    assert called is False


def test_new_dataset_is_allowed_and_uses_deterministic_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prior = tmp_path / "prior.csv"
    current = tmp_path / "current.csv"
    prior.write_text("prior", encoding="utf-8")
    current.write_text("current", encoding="utf-8")
    store = ExperienceStore(":memory:")
    store.record_experiment(
        experiment_id="prior",
        created_at_utc="2026-01-01T00:00:00Z",
        hypothesis_name="validation-hypothesis",
        symbol="EURUSD",
        timeframe="1D",
        final_decision="REJECT",
        record=_record(prior),
    )

    captured = {}

    sentinel = object()

    def fake_run_experiment(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(module, "run_experiment", fake_run_experiment)

    result = module.run_independent_validation(
        csv_path=current,
        hypothesis=_hypothesis(),
        signal=lambda bars, index: False,
        memory_store=store,
        strategy_version="v1",
    )

    assert result.gate.disposition == "INDEPENDENT_VALIDATION"
    assert result.experiment is sentinel
    assert captured["csv_path"] == str(current)
    assert captured["strategy_version"] == "v1"
    assert captured["memory_store"] is store
