from trading_research.experiment2b_momentum_confirmation import END_UTC, START_UTC, FEE_BPS, SLIPPAGE_BPS


def test_experiment2b_window_and_costs_are_frozen():
    assert START_UTC == "2026-01-01T00:00:00+00:00"
    assert END_UTC == "2026-08-20T23:59:59+00:00"
    assert FEE_BPS == 1.0
    assert SLIPPAGE_BPS == 1.0


def test_experiment2b_is_momentum_only():
    module = __import__("trading_research.experiment2b_momentum_confirmation", fromlist=["momentum_signal_series"])
    assert hasattr(module, "momentum_signal_series")
