from datetime import datetime, timedelta, timezone

import pytest

from trading_research.data import Bar
from trading_research.regime_conditioned_research import run_development_regime_research
from trading_research.research_brain import ExperimentPlan


def plan() -> ExperimentPlan:
    return ExperimentPlan(
        family="regime_conditioned_continuation",
        event_move_threshold_bps=50,
        horizon_bars=1,
        regime_method="trend_volatility",
        trend_lookback_bars=20,
        trend_gap_threshold_bps=50,
        volatility_lookback_bars=20,
        volatility_percentile=0.75,
        minimum_events_per_regime=20,
        exploration_budget=5,
        selection_rule="max_lower_95ci_effect_after_costs",
        confirmation_plan="untouched_single_test",
    )


def synthetic_bars(count: int = 400) -> list[Bar]:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    prices = []
    price = 100.0
    for i in range(count):
        if 100 <= i < 220:
            step = 0.8 if i % 2 == 0 else 0.7
        else:
            step = -0.7 if i % 3 == 0 else 0.25
        open_price = price
        close = price + step
        high = max(open_price, close) + 0.15
        low = min(open_price, close) - 0.15
        prices.append(
            Bar(
                timestamp=start + timedelta(hours=4 * i),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
            )
        )
        price = close
    return prices


def test_research_is_bounded_and_records_every_variant():
    result = run_development_regime_research(synthetic_bars(), plan())
    assert result.candidates_tested == 5
    assert result.exploration_budget == 5
    assert len(result.candidates) == 5
    assert result.selected_candidate_id in {None, *(candidate.candidate_id for candidate in result.candidates)}
    assert all(candidate.candidate_id.startswith("regime-") for candidate in result.candidates)


def test_confirmation_is_not_part_of_development_runner():
    result = run_development_regime_research(synthetic_bars(), plan(), transaction_cost_bps=4.0)
    assert result.conclusion in {
        "DEVELOPMENT_CANDIDATE_SELECTED_NOT_CONFIRMED",
        "NO_POSITIVE_DEVELOPMENT_EFFECT",
        "INCONCLUSIVE_NO_CANDIDATE_WITH_MINIMUM_EVENTS",
    }


def test_plan_rejects_unbounded_selection_rule():
    with pytest.raises(ValueError):
        ExperimentPlan.from_dict({
            "family": "regime_conditioned_continuation",
            "event_move_threshold_bps": 50,
            "horizon_bars": 1,
            "regime_method": "trend_volatility",
            "trend_lookback_bars": 20,
            "trend_gap_threshold_bps": 50,
            "volatility_lookback_bars": 20,
            "volatility_percentile": 0.75,
            "minimum_events_per_regime": 20,
            "exploration_budget": 5,
            "selection_rule": "choose_the_best_result",
            "confirmation_plan": "untouched_single_test",
        })
