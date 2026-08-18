import unittest

from trading_research.contracts import (
    BacktestMetrics,
    Decision,
    Hypothesis,
    ResearchGates,
    evaluate_gate,
)


class TradingResearchContractTests(unittest.TestCase):
    def test_hypothesis_requires_falsifiable_fields(self):
        hypothesis = Hypothesis(
            name="trend-following",
            thesis="Momentum persists after a confirmed breakout.",
            symbol="EURUSD",
            timeframe="H1",
            rules={
                "entry": "close above previous 20-bar high",
                "exit": "close below previous 10-bar low",
            },
            expected_edge="Continuation after directional breakouts.",
            falsifier="Out-of-sample expectancy is not positive.",
        )
        hypothesis.validate()

    def test_weak_strategy_is_rejected_with_reasons(self):
        metrics = BacktestMetrics(
            trades=37,
            net_return=-0.04,
            max_drawdown=0.31,
            profit_factor=0.82,
            expectancy=-0.002,
            win_rate=0.32,
            average_win=0.008,
            average_loss=-0.007,
        )
        decision = evaluate_gate(metrics, ResearchGates())
        self.assertEqual(decision.decision, Decision.REJECT)
        self.assertTrue(any(reason.startswith("too_few_trades") for reason in decision.reasons))
        self.assertTrue(any(reason.startswith("profit_factor_below_gate") for reason in decision.reasons))
        self.assertTrue(any(reason.startswith("drawdown_above_gate") for reason in decision.reasons))

    def test_insufficient_sample_without_performance_failure_is_inconclusive(self):
        metrics = BacktestMetrics(
            trades=20,
            net_return=0.03,
            max_drawdown=0.10,
            profit_factor=1.40,
            expectancy=0.001,
            win_rate=0.45,
            average_win=0.009,
            average_loss=-0.006,
        )
        decision = evaluate_gate(metrics, ResearchGates())
        self.assertEqual(decision.decision, Decision.INCONCLUSIVE)
        self.assertTrue(any(reason.startswith("too_few_trades") for reason in decision.reasons))
        self.assertIn("insufficient_sample_for_promotion", decision.reasons)

    def test_candidate_passing_initial_gate_is_promising_not_proven(self):
        metrics = BacktestMetrics(
            trades=240,
            net_return=0.18,
            max_drawdown=0.16,
            profit_factor=1.28,
            expectancy=0.0015,
            win_rate=0.43,
            average_win=0.009,
            average_loss=-0.006,
        )
        decision = evaluate_gate(metrics, ResearchGates())
        self.assertEqual(decision.decision, Decision.PROMISING)
        self.assertEqual(tuple(decision.reasons), ("all_initial_gates_passed",))

    def test_invalid_metrics_are_rejected_before_decision(self):
        metrics = BacktestMetrics(
            trades=10,
            net_return=0.01,
            max_drawdown=0.1,
            profit_factor=-1.0,
            expectancy=0.0,
            win_rate=0.5,
            average_win=0.01,
            average_loss=-0.01,
        )
        with self.assertRaises(ValueError):
            evaluate_gate(metrics, ResearchGates())


if __name__ == "__main__":
    unittest.main()
