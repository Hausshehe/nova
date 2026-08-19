from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.escalation_efficiency import evaluate_efficiency


def test_efficiency_counts_requests_and_opportunities():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [
        Bar(base + timedelta(minutes=i), 1.0 + i * 0.0001, 1.0, 1.0, 1.0 + i * 0.0001, 1)
        for i in range(6)
    ]
    report = evaluate_efficiency(
        bars,
        opportunity_move_bps=1.0,
        future_bars=2,
    )
    assert report.ai_requests >= 0
    assert report.unnecessary_ai_requests >= 0
    assert 0.0 <= report.precision <= 1.0
    assert 0.0 <= report.recall <= 1.0
