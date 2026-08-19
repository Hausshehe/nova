from trading_research.data import Bar
from trading_research.online_horizon_expert_ensemble import evaluate_online_horizon_expert_ensemble

def test_horizon_ensemble_schema_and_causality():
    bars = [Bar(timestamp=str(i), open=100+i*0.01, high=101+i*0.01, low=99+i*0.01, close=100+i*0.01) for i in range(300)]
    result = evaluate_online_horizon_expert_ensemble(bars, min_history=5, horizons=(2, 4), folds=2)
    assert result["candidate_bars"] > 0
    assert result["horizons"] == (2, 4)
    assert "selected_horizon_counts" in result
    assert len(result["fold_net_returns"]) == 2

def test_invalid_horizon_rejected():
    bars = [Bar(timestamp=str(i), open=100, high=101, low=99, close=100) for i in range(100)]
    try:
        evaluate_online_horizon_expert_ensemble(bars, horizons=(0,))
    except ValueError:
        return
    raise AssertionError("invalid horizon should fail")
