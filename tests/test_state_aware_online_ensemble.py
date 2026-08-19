from trading_research.data import Bar
from trading_research.state_aware_online_horizon_ensemble import evaluate_state_aware_online_ensemble


def test_state_aware_ensemble_validates_parameters():
    bars = [Bar(i, 1.0 + i * 0.001, 1.0 + i * 0.001, 1.0 + i * 0.001, 1.0 + i * 0.001) for i in range(60)]
    result = evaluate_state_aware_online_ensemble(bars, min_history=1)
    assert result["candidate_bars"] >= 0


def test_state_state_count_is_consistent():
    bars = [Bar(i, 1.0 + i * 0.001, 1.0 + i * 0.001, 1.0 + i * 0.001, 1.0 + i * 0.001) for i in range(80)]
    result = evaluate_state_aware_online_ensemble(bars, min_history=1)
    assert sum(result["state_counts"].values()) == result["decisions"]
