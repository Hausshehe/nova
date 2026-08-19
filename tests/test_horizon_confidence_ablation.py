from trading_research.data import Bar
from trading_research.horizon_confidence_ablation import evaluate_horizon_confidence_ablation


def test_horizon_confidence_ablation_schema() -> None:
    bars = [Bar(timestamp=f"2020-01-{i+1:02d}", open=1.0, high=1.01, low=0.99, close=1.0 + i * 0.001) for i in range(40)]
    result = evaluate_horizon_confidence_ablation(bars, thresholds=(0.0, 1.0), min_history=2)
    assert result["policy"] == "causal_horizon_confidence_ablation"
    assert set(result["results"]) == {"0.0", "1.0"}
    for value in result["results"].values():
        assert value["decisions"] >= 0
        assert 0.0 <= value["decision_rate"] <= 1.0
