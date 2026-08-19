from trading_research.data import Bar
from trading_research.consensus_direction_policy import evaluate_consensus_direction


def _bars(n=90):
    return [Bar(f"2020-01-{(i % 28) + 1:02d}", 1, 1, 1, 1, 1) for i in range(n)]


def test_consensus_report_shape():
    result = evaluate_consensus_direction(_bars())
    assert result["policy"] == "causal_fixed_expert_consensus"
    assert result["agreement_required"] == 6
    assert len(result["fold_net_returns"]) == 4
