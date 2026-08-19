from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.opportunity_recall import evaluate_opportunity_recall


def _bar(index: int, close: float) -> Bar:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * index)
    return Bar(timestamp, close, close, close, close, 1.0)


def test_recall_detects_large_move_with_ai_review():
    bars = [_bar(0, 100.0), _bar(1, 100.05), _bar(2, 100.1), _bar(3, 100.15), _bar(4, 100.7)]
    report = evaluate_opportunity_recall(bars, future_bars=2, opportunity_move_bps=30.0)
    assert report.opportunities >= 1
    assert report.opportunities_with_ai_review >= 1
    assert report.recall > 0.0


def test_empty_input_is_safe():
    report = evaluate_opportunity_recall([])
    assert report.opportunities == 0
    assert report.missed_opportunities == 0
    assert report.recall == 0.0


def test_invalid_parameters_are_rejected():
    bars = [_bar(0, 100.0)]
    try:
        evaluate_opportunity_recall(bars, future_bars=0)
    except ValueError:
        pass
    else:
        raise AssertionError("future_bars=0 must fail")
