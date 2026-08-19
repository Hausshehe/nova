from trading_research.horizon_adaptation_ablation import CONFIGURATIONS, evaluate_horizon_adaptation_ablation
from trading_research.data import Bar


def test_configurations_are_fixed():
    assert CONFIGURATIONS == {"fixed_2": (2,), "fixed_4": (4,), "fixed_8": (8,), "adaptive_2_4_8": (2, 4, 8)}


def test_ablation_returns_all_configurations():
    bars = [Bar(timestamp=i, open=1.0, high=1.001, low=0.999, close=1.0 + i * 0.0001, volume=1.0) for i in range(80)]
    result = evaluate_horizon_adaptation_ablation(bars, min_history=1)
    assert result["configurations"] == list(CONFIGURATIONS)
    assert set(result["results"]) == set(CONFIGURATIONS)
