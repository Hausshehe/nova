from trading_research.research_decision_auditor import audit_decision
from trading_research.research_state import ResearchState


def state():
    return ResearchState(
        research_question="Does XAGUSD contain a robust short-horizon effect?",
        asset="XAGUSD",
        timeframe="4H",
        data_boundaries="development until confirmation lock",
        prohibited_experiments={"simple_continuation", "simple_mean_reversion"},
        tested_experiments={"simple_continuation", "simple_mean_reversion"},
        exploration_budget_remaining=8,
    )


def good_decision():
    return {
        "question": "Does XAGUSD contain a robust short-horizon effect?",
        "problem_interpretation": "Test conditional predictability rather than a specific indicator.",
        "premise_challenges": ["Nonstationarity", "Costs can erase the effect."],
        "mechanisms": [
            {"id": "m1", "mechanism": "temporary overshoot", "prediction": "shock followed by reversal", "disconfirming_observation": "no reversal after controls"},
            {"id": "m2", "mechanism": "information diffusion", "prediction": "shock followed by continuation", "disconfirming_observation": "no continuation after controls"},
        ],
        "experiment_candidates": [
            {"id": "e1", "name": "event response", "mechanisms_separated": ["m1", "m2"], "development_only": True, "estimated_information_value": 0.9, "estimated_cost": 0.2, "overfitting_risk": 0.2},
            {"id": "e2", "name": "indicator sweep", "mechanisms_separated": ["m1", "m2"], "development_only": True, "estimated_information_value": 0.3, "estimated_cost": 0.6, "overfitting_risk": 0.4},
        ],
        "selected_experiment_id": "e1",
        "selection_rationale": "It directly separates the competing mechanisms.",
        "falsification_rule": "Reject if the preregistered effect is absent after costs.",
        "stopping_rule": "Stop after repeated independent failures.",
        "confirmation_protection": "Never inspect confirmation until the formulation is locked.",
        "next_action": "TEST",
        "state_update_expectation": "Update mechanism confidence from the result.",
    }


def test_good_decision_passes():
    result = audit_decision(good_decision(), state())
    assert result.passed
    assert not result.critical_failures


def test_repeated_or_prohibited_experiment_fails():
    decision = good_decision()
    decision["selected_experiment_id"] = "simple_continuation"
    decision["experiment_candidates"][0]["id"] = "simple_continuation"
    result = audit_decision(decision, state())
    assert not result.passed
    assert "selected_experiment_already_tested" in result.critical_failures
    assert "selected_experiment_prohibited" in result.critical_failures


def test_missing_stopping_rule_fails():
    decision = good_decision()
    decision["stopping_rule"] = ""
    result = audit_decision(decision, state())
    assert not result.passed
    assert "missing_stopping_rule" in result.critical_failures


def test_non_discriminating_selected_experiment_fails():
    decision = good_decision()
    decision["experiment_candidates"][0]["mechanisms_separated"] = ["m1"]
    result = audit_decision(decision, state())
    assert not result.passed
    assert "selected_experiment_does_not_discriminate" in result.critical_failures


def test_unknown_mechanism_reference_fails():
    decision = good_decision()
    decision["experiment_candidates"][0]["mechanisms_separated"] = ["m1", "unknown"]
    result = audit_decision(decision, state())
    assert not result.passed
    assert "selected_experiment_separates_unknown_mechanisms" in result.critical_failures
