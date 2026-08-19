from datetime import datetime, timezone

from trading_research.data import Bar
from trading_research.escalation_calibration import calibrate


def test_calibration_returns_points_for_each_threshold() -> None:
    bars = [
        Bar(datetime(2026, 1, 1, tzinfo=timezone.utc), 1.0, 1.001, 0.999, 1.0, 1),
        Bar(datetime(2026, 1, 2, tzinfo=timezone.utc), 1.0, 1.001, 0.999, 1.002, 1),
        Bar(datetime(2026, 1, 3, tzinfo=timezone.utc), 1.002, 1.003, 1.001, 1.004, 1),
    ]
    points = calibrate(bars, thresholds_bps=(10.0, 30.0))
    assert [point.opportunity_move_bps for point in points] == [10.0, 30.0]
    assert all(0.0 <= point.recall <= 1.0 for point in points)
    assert all(point.missed_opportunities >= 0 for point in points)
