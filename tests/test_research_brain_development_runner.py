from datetime import datetime, timezone

from trading_research.research_brain import ExperimentPlan, ResearchBrief
from tools.run_research_brain_development import (
    DEVELOPMENT_END_UTC,
    DEVELOPMENT_START_UTC,
    SYMBOL,
    TIMEFRAME,
    _brief_payload,
)


def _brief() -> ResearchBrief:
    plan = ExperimentPlan(
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
    return ResearchBrief(
        research_question="q",
        mechanism="m",
        hypothesis="h",
        why_it_might_work="w",
        what_would_falsify_it="f",
        primary_test="t",
        development_only_exploration=("x",),
        confirmation_rule="one untouched confirmation test",
        key_risks=("r",),
        research_priority="HIGH",
        next_action="TEST",
        experiment_plan=plan,
    )


def test_development_window_is_fixed_before_confirmation_period():
    start = datetime.fromisoformat(DEVELOPMENT_START_UTC)
    end = datetime.fromisoformat(DEVELOPMENT_END_UTC)
    assert start.tzinfo == timezone.utc
    assert end.tzinfo == timezone.utc
    assert start < end
    assert DEVELOPMENT_END_UTC == "2023-01-01T00:00:00+00:00"


def test_runner_payload_preserves_plan_and_research_boundaries():
    payload = _brief_payload(_brief())
    assert payload["experiment_plan"]["selection_rule"] == "max_lower_95ci_effect_after_costs"
    assert payload["experiment_plan"]["confirmation_plan"] == "untouched_single_test"
    assert "confirmation data" in payload["confirmation_rule"]
    assert SYMBOL == "XAGUSD"
    assert TIMEFRAME == "4H"
