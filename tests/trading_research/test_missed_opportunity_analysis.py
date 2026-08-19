from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.missed_opportunity_analysis import analyze_missed_opportunities


def _bars() -> tuple[Bar, ...]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        Bar(base + timedelta(days=i), 1.0 + i * 0.0001, 1.0 + i * 0.0002,
            1.0 + i * 0.00005, 1.0 + i * 0.0001, 1.0)
        for i in range(60)
    ]
    return tuple(rows)


def test_analysis_returns_consistent_counts() -> None:
    report = analyze_missed_opportunities(_bars())
    assert report.actionable_opportunities >= report.reviewed_actionable
    assert report.missed_actionable >= 0
    assert sum(report.causes.values()) == report.missed_actionable
