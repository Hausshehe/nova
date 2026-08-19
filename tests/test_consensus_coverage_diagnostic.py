from trading_research.consensus_coverage_diagnostic import evaluate_consensus_coverage
from trading_research.data import Bar


def test_consensus_coverage_report() -> None:
    bars = [Bar("2020-01-01", 1, 1, 1, 1 + i * 0.0001) for i in range(100)]
    result = evaluate_consensus_coverage(bars)
    assert result["policy"] == "causal_consensus_coverage_diagnostic"
    assert "agreement_histogram" in result
    assert result["causal_rule"]
