import json

import pytest

from trading_research.research_brain import (
    ResearchBrain,
    ResearchQuestion,
    ResearchBrief,
    ExperimentPlan,
    build_research_brain_prompt,
)


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, request_payload):
        self.calls.append(request_payload)
        return {"choices": [{"message": {"content": json.dumps(self.payload)}}]}


class FallbackTransport:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, request_payload):
        self.calls.append(request_payload)
        if len(self.calls) == 1:
            raise RuntimeError("Groq API HTTP 403: error code: 1010")
        return {"choices": [{"message": {"content": json.dumps(self.payload)}}]}


def valid_plan():
    return {
        "family": "regime_conditioned_continuation",
        "event_move_threshold_bps": 50,
        "horizon_bars": 1,
        "regime_method": "trend_volatility",
        "trend_lookback_bars": 20,
        "trend_gap_threshold_bps": 50,
        "volatility_lookback_bars": 20,
        "volatility_percentile": 0.75,
        "minimum_events_per_regime": 50,
        "exploration_budget": 12,
        "selection_rule": "max_lower_95ci_effect_after_costs",
        "confirmation_plan": "untouched_single_test",
    }


def valid_payload():
    return {
        "research_question": "Does a volatility-conditioned reversal effect exist?",
        "mechanism": "Overshoot may be followed by short-term correction when volatility is unusually high.",
        "hypothesis": "After an unusually large standardized move, the next bar mean-reverts more often in a high-volatility regime.",
        "why_it_might_work": "Liquidity shocks and temporary inventory imbalance can create short-lived overshoots.",
        "what_would_falsify_it": "The effect disappears after realistic costs or is absent in all preregistered development folds.",
        "primary_test": "Measure forward continuation probability after the signal on development data with costs specified before testing.",
        "development_only_exploration": [
            "Compare a bounded preregistered set of event thresholds on development data.",
            "Test the effect separately by the deterministic trend/volatility regime on development data only.",
        ],
        "confirmation_rule": "After locking one formulation, run it once on untouched confirmation data with no parameter changes based on that result.",
        "key_risks": [
            "Multiple testing can create a false positive.",
            "The effect may be regime-specific rather than persistent.",
        ],
        "research_priority": "HIGH",
        "next_action": "TEST",
        "experiment_plan": valid_plan(),
    }


def test_brief_parses_and_preserves_boundaries():
    transport = FakeTransport(valid_payload())
    brain = ResearchBrain(api_key="test", transport=transport)
    brief = brain.investigate(
        ResearchQuestion(
            question="Find evidence of a short-horizon reversal mechanism.",
            symbol="XAGUSD",
            timeframe="4H",
        )
    )
    assert isinstance(brief, ResearchBrief)
    assert brief.next_action == "TEST"
    assert brief.research_priority == "HIGH"
    assert len(brief.development_only_exploration) == 2
    assert brief.experiment_plan.exploration_budget == 12
    assert brief.experiment_plan.selection_rule == "max_lower_95ci_effect_after_costs"
    assert "untouched confirmation" in brief.confirmation_rule.lower()
    assert transport.calls[0]["response_format"]["type"] == "json_schema"
    assert transport.calls[0]["max_completion_tokens"] == 4096
    assert transport.calls[0]["reasoning_effort"] == "low"
    assert "reasoning_format" not in transport.calls[0]


def test_http_403_falls_back_to_json_object_and_local_validation():
    transport = FallbackTransport(valid_payload())
    brain = ResearchBrain(api_key="test", transport=transport)
    brief = brain.investigate(
        ResearchQuestion(
            question="Find evidence of a regime-conditioned effect.",
            symbol="XAGUSD",
            timeframe="4H",
        )
    )
    assert brief.next_action == "TEST"
    assert len(transport.calls) == 2
    assert transport.calls[0]["response_format"]["type"] == "json_schema"
    assert transport.calls[1]["response_format"] == {"type": "json_object"}


def test_question_requires_core_fields():
    with pytest.raises(ValueError):
        ResearchQuestion(question="", symbol="XAGUSD", timeframe="4H").validate()


def test_prompt_contains_the_non_negotiable_research_rules():
    prompt = build_research_brain_prompt(
        ResearchQuestion(
            question="Investigate a market mechanism.",
            symbol="XAGUSD",
            timeframe="4H",
        )
    )
    assert "Separate discovery from confirmation" in prompt
    assert "confirmation data must" in prompt.lower()
    assert "No edge found" in prompt
    assert "Do not claim that a candidate is a real edge" in prompt
    assert "Return exactly one JSON object matching this schema" in prompt
    assert "selection rule is fixed before results are seen" in prompt


def test_invalid_action_is_rejected():
    payload = valid_payload()
    payload["next_action"] = "BUY_EVERYTHING"
    with pytest.raises(ValueError):
        ResearchBrief.from_dict(payload)


def test_experiment_plan_rejects_adaptive_selection_rule():
    payload = valid_plan()
    payload["selection_rule"] = "pick_the_best_backtest"
    with pytest.raises(ValueError):
        ExperimentPlan.from_dict(payload)
