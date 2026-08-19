from pathlib import Path

from trading_research.data import Bar
from trading_research.opportunity_recall import evaluate_opportunity_recall


def _bars(closes: list[float]) -> list[Bar]:
    from datetime import datetime, timedelta, timezone

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(minutes=15 * i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1.0,
        )
        for i, close in enumerate(closes)
    ]


def test_recall_counts_future_move_and_prior_review_window() -> None:
    bars = _bars([100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.6, 100.7, 100.8])
    report = evaluate_opportunity_recall(
        bars,
        future_bars=2,
        opportunity_move_bps=30.0,
    )

    assert report.opportunities > 0
    assert 0.0 <= report.recall <= 1.0
    assert report.missed_opportunities == report.opportunities - report.opportunities_with_ai_review


def test_empty_data_has_zero_recall() -> None:
    report = evaluate_opportunity_recall([], future_bars=2, opportunity_move_bps=30.0)
    assert report.opportunities == 0
    assert report.ai_requests == 0
    assert report.recall == 0.0
