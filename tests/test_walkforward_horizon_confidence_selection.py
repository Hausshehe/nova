from trading_research.walkforward_horizon_confidence_selection import THRESHOLDS


def test_thresholds_are_fixed_and_nonempty():
    assert THRESHOLDS == (0.0, 1.0, 2.0, 4.0)
