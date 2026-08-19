from trading_research.directional_policy_family import evaluate_directional_policy_family
from trading_research.data import Bar


def _bars(n=80):
    return tuple(
        Bar(timestamp=f"2020-01-{(i % 28) + 1:02d}", open=100+i*0.1, high=101+i*0.1, low=99+i*0.1, close=100+i*0.1, volume=1)
        for i in range(n)
    )


def test_policy_family_is_fixed_and_returns_all_policies():
    result = evaluate_directional_policy_family(_bars(), folds=4)
    assert [item.policy for item in result] == [
        "sma_both", "sma_long_only", "sma_short_only", "sma_mom4_agree", "sma_mom8_agree"
    ]
    assert all(item.decisions >= 0 for item in result)
    assert all(len(item.fold_net_returns) == 4 for item in result)
