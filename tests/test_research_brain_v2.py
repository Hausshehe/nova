import json

import pytest

from trading_research.research_brain_v2 import ResearchBrainV2, ResearchRequest, validate_decision
from trading_research.research_state import ResearchState


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, request_payload):
        self.calls.append(request_payload)
        return {"choices": [{"message": {"content": json.dumps(self.payload)}}]}


def state():
    return ResearchState(
        research_question="Does XAGUSD contain a robust short-horizon effect?",
        asset="XAGUSD",
        timeframe="4H",
        data_boundaries="development data only until confirmation lock",
        exploration_budget_remaining=8,
    )


def payload():
    return {
        "question": "Does XAGUSD contain a robust short-horizon effect?",
        "problem_interpretation": "The question is about conditional predictability, not a specific indicator strategy.",
        "premise_challenges": [
            "A historical pattern may be nonstationary.",
            "Apparent predictability may be compensation for volatility or costs.",
        ],
        "mechanisms": [
            {"id": "m1", "mechanism": "temporary price overshoot", "causal_story": "Liquidity imbalance can temporarily push price away from short-run equilibrium.", "prediction": "large shocks are followed by partial reversal under suitable conditions", "disconfirming_observation": "no reversal after controlling for volatility and costs", "current_confidence": 0.45, "status": "candidate", "why_testable": "event-conditioned forward returns can distinguish it"},
            {"id": "m2", "mechanism": "information continuation", "causal_story": "Information may diffuse over multiple bars rather than all at once.", "prediction": "large directional moves are followed by continuation under suitable conditions", "disconfirming_observation": "continuation disappears after controlling for event size and regime", "current_confidence": 0.4, "status": "candidate", "why_testable": "the sign and path of forward returns differ from reversal"},
        ],
        "experiment_candidates": [
            {"id": "e1", "name": "event-conditioned directional response", "question_discriminated": "Which of m1 or m2 better predicts the next-bar response after large moves?", "mechanisms_separated": ["m1", "m2"], "outcome": "net forward return and sign probability", "horizon": "1 bar", "development_only": True, "estimated_information_value": 0.9, "estimated_cost": 0.2, "overfitting_risk": 0.2, "confounders": ["volatility regime", "spread/cost"]},
            {"id": "e2", "name": "unconditional indicator sweep", "question_discriminated": "Whether any technical indicator appears profitable", "mechanisms_separated": ["m1", "m2"], "outcome": "development backtest return", "horizon": "varied", "development_only": True, "estimated_information_value": 0.2, "estimated_cost": 0.5, "overfitting_risk": 0.9, "confounders": ["multiple testing"]},
        ],
        "selected_experiment_id": "e1",
        "selection_rationale": "e1 directly discriminates the competing mechanisms with lower search risk.",
        "falsification_rule": "Reject the mechanism if the preregistered conditional effect is consistently absent after costs.",
        "stopping_rule": "Stop the branch after repeated independent tests fail to support either mechanism.",
        "confirmation_protection": "Do not inspect or optimize against confirmation data before locking the formulation.",
        "next_action": "TEST",
        "state_update_expectation": "Update mechanism confidence and mark e1 as tested using the observed uncertainty-aware result.",
    }


def test_v2_requires_distinct_mechanisms_and_selects_new_experiment():
    transport = FakeTransport(payload())
    brain = ResearchBrainV2(api_key="test", transport=transport)
    decision = brain.decide(ResearchRequest("Research", "XAGUSD", "4H"), state())
    assert decision["selected_experiment_id"] == "e1"
    assert len(decision["mechanisms"]) >= 2
    assert transport.calls[0]["response_format"]["type"] == "json_schema"
    assert transport.calls[0]["max_completion_tokens"] == 6144
    assert transport.calls[0]["reasoning_effort"] == "high"


def test_v2_rejects_repeated_experiment():
    s = state()
    s.tested_experiments.add("e1")
    with pytest.raises(ValueError, match="already been tested"):
        validate_decision(payload(), s)


def test_v2_rejects_experiment_that_does_not_discriminate():
    p = payload()
    p["experiment_candidates"][0]["mechanisms_separated"] = ["m1"]
    with pytest.raises(ValueError, match="separate at least two mechanisms"):
        validate_decision(p, state())


def test_v2_rejects_unknown_mechanism_reference():
    p = payload()
    p["experiment_candidates"][0]["mechanisms_separated"] = ["m1", "unknown"]
    with pytest.raises(ValueError, match="unknown mechanism ids"):
        validate_decision(p, state())


def test_v2_rejects_duplicate_ids():
    p = payload()
    p["mechanisms"][1]["id"] = "m1"
    with pytest.raises(ValueError, match="mechanism ids must be unique"):
        validate_decision(p, state())


def test_v2_blocks_development_after_confirmation_lock():
    s = state()
    s.confirmation_locked = True
    with pytest.raises(ValueError, match="confirmation is locked"):
        validate_decision(payload(), s)


def test_prompt_contains_information_value_and_stop_rules():
    from trading_research.research_brain_v2 import build_prompt
    text = build_prompt(ResearchRequest("Research", "XAGUSD", "4H"), state())
    assert "information value" in text
    assert "STOP is legitimate" in text
    assert "genuinely different causal mechanisms" in text
    assert "Never repeat a prohibited" in text
