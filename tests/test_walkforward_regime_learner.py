from trading_research.data import Bar
from trading_research.walkforward_regime_learner import evaluate_walkforward_regime_direction


def _bars(n: int = 700) -> list[Bar]:
    return [Bar("2020-01-01", 1, 1, 1, 1) for _ in range(n)]


def test_regime_learner_returns_report() -> None:
    result = evaluate_walkforward_regime_direction(_bars())
    assert result["policy"] == "causal_walkforward_regime_direction"
    assert result["decisions"] >= 0
    assert len(result["fold_net_returns"]) == 4
    assert result["causal_rule"]
