import pytest

from trading_research.research_state import EvidenceRecord, MechanismRecord, ResearchState


def make_state():
    return ResearchState(
        research_question="Investigate a short-horizon XAGUSD relationship.",
        asset="XAGUSD",
        timeframe="4H",
        data_boundaries="Development is separate from untouched confirmation.",
        exploration_budget_remaining=3,
    )


def test_state_tracks_mechanisms_and_evidence():
    state = make_state()
    state.add_mechanism(
        MechanismRecord(
            id="m1",
            statement="Temporary shock imbalance may create short-horizon reversal.",
            predictions=["Large shocks should be followed by negative autocorrelation."],
            status="active",
        )
    )
    state.add_evidence(
        EvidenceRecord(
            id="e1",
            experiment_id="exp1",
            data_role="development",
            result="Observed modest reversal.",
            uncertainty="Wide interval.",
            cost_assumptions="Fixed realistic spread and slippage.",
            interpretation="Weak support, not confirmation.",
            limitations="Single development period.",
            what_it_changes="Keep m1 active but uncertain.",
        )
    )
    assert "m1" in state.mechanisms
    assert "exp1" in state.tested_experiments
    assert state.development_available()


def test_confirmation_locks_development_state():
    state = make_state()
    state.add_evidence(
        EvidenceRecord(
            id="c1",
            experiment_id="exp-confirm",
            data_role="confirmation",
            result="Neutral.",
            uncertainty="Large.",
            cost_assumptions="Predeclared.",
            interpretation="No confirmation.",
            limitations="One confirmation sample.",
            what_it_changes="Candidate remains unconfirmed.",
        )
    )
    assert state.confirmation_locked
    assert not state.development_available()


def test_prohibited_experiment_is_rejected():
    state = make_state()
    state.prohibit_experiment("exp-family-1")
    with pytest.raises(ValueError, match="prohibited"):
        state.add_evidence(
            EvidenceRecord(
                id="e2",
                experiment_id="exp-family-1",
                data_role="development",
                result="x",
                uncertainty="x",
                cost_assumptions="x",
                interpretation="x",
                limitations="x",
                what_it_changes="x",
            )
        )


def test_rejecting_mechanism_requires_reason():
    state = make_state()
    state.add_mechanism(
        MechanismRecord(
            id="m1",
            statement="A mechanism.",
            predictions=["Prediction."],
        )
    )
    with pytest.raises(ValueError):
        state.reject_mechanism("m1", "")

    state.reject_mechanism("m1", "Repeated independent formulations failed.")
    assert state.mechanisms["m1"].status == "rejected"
    assert "m1" in state.rejected_mechanisms


def test_to_dict_exposes_research_space_and_confirmation_protection():
    state = make_state()
    state.prohibit_experiment("exp-old")
    payload = state.to_dict()
    assert "exp-old" in payload["research_space"]["prohibited_experiments"]
    assert payload["confirmation_protection"]["locked"] is False
