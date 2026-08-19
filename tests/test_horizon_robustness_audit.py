from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.horizon_robustness_audit import _cost_sensitivity, _non_overlapping, audit_fixed_8_vs_alternatives
from trading_research.online_horizon_expert_ensemble import HorizonPrediction


def _bars(count: int = 40) -> list[Bar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(minutes=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.0 + index,
            volume=1.0,
        )
        for index in range(count)
    ]


def _prediction(index: int, horizon: int = 8) -> HorizonPrediction:
    return HorizonPrediction(index, "mom8", horizon, "LONG", 1.0, 10.0)


def test_non_overlapping_skips_predictions_inside_previous_horizon() -> None:
    predictions = (_prediction(2), _prediction(5), _prediction(10), _prediction(18))
    accepted = _non_overlapping(predictions)
    assert [prediction.index for prediction in accepted] == [2, 10, 18]


def test_frozen_cost_sensitivity_does_not_change_decision_count(monkeypatch) -> None:
    candidate_indices = {10, 20, 30}
    monkeypatch.setattr(
        "trading_research.horizon_robustness_audit.high_recall_candidate_indices",
        lambda *args, **kwargs: candidate_indices,
    )
    monkeypatch.setattr(
        "trading_research.online_horizon_expert_ensemble.high_recall_candidate_indices",
        lambda *args, **kwargs: candidate_indices,
    )

    result = audit_fixed_8_vs_alternatives(
        _bars(),
        training_cost_bps=4.0,
        cost_grid_bps=(0.0, 4.0, 8.0),
        min_history=0,
    )
    fixed = result["configurations"]["online_expert_fixed_8"]
    assert fixed["cost_sensitivity"]["0.0"]["decisions"] == fixed["decisions"]
    assert fixed["cost_sensitivity"]["4.0"]["decisions"] == fixed["decisions"]
    assert fixed["cost_sensitivity"]["8.0"]["decisions"] == fixed["decisions"]


def test_cost_grid_reduces_mean_net_by_exact_cost_delta() -> None:
    predictions = (_prediction(10), _prediction(20))
    result = _cost_sensitivity(
        predictions,
        bar_count=40,
        folds=4,
        cost_grid_bps=(0.0, 2.0, 4.0),
    )
    assert result["0.0"]["mean_net_return_bps"] == result["4.0"]["mean_net_return_bps"] + 4.0
    assert result["2.0"]["mean_net_return_bps"] == result["4.0"]["mean_net_return_bps"] + 2.0


def test_audit_marks_results_as_diagnostic_only(monkeypatch) -> None:
    candidate_indices = {10, 20, 30}
    monkeypatch.setattr(
        "trading_research.horizon_robustness_audit.high_recall_candidate_indices",
        lambda *args, **kwargs: candidate_indices,
    )
    monkeypatch.setattr(
        "trading_research.online_horizon_expert_ensemble.high_recall_candidate_indices",
        lambda *args, **kwargs: candidate_indices,
    )

    result = audit_fixed_8_vs_alternatives(_bars(), min_history=0)
    assert result["research_status"] == "diagnostic_only"
    assert "online_expert_fixed_8" in result["configurations"]
    assert "online_expert_adaptive_2_4_8" in result["configurations"]
