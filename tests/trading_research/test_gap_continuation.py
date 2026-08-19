from datetime import datetime, timezone

from trading_research.data import Bar
from trading_research.gap_continuation import GapContinuationSignal


def bar(timestamp: str, open_: float, close: float) -> Bar:
    high = max(open_, close)
    low = min(open_, close)
    return Bar(
        timestamp=datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def test_positive_gap_requests_long_for_one_subsequent_bar() -> None:
    bars = [
        bar("2024-01-02T00:00:00", 1.1000, 1.1020),
        bar("2024-01-03T00:00:00", 1.1050, 1.1030),  # positive opening gap
        bar("2024-01-04T00:00:00", 1.1040, 1.1060),
        bar("2024-01-05T00:00:00", 1.1070, 1.1080),
    ]
    signal = GapContinuationSignal()
    assert signal(bars, 0) is False
    assert signal(bars, 1) is True
    assert signal(bars, 2) is False
    assert signal(bars, 3) is False


def test_non_positive_gap_does_not_request_long() -> None:
    bars = [
        bar("2024-01-02T00:00:00", 1.1000, 1.1050),
        bar("2024-01-03T00:00:00", 1.1040, 1.1030),  # no positive gap
        bar("2024-01-04T00:00:00", 1.1020, 1.1060),
    ]
    signal = GapContinuationSignal()
    assert signal(bars, 1) is False
    assert signal(bars, 2) is False


def test_signal_requires_chronological_evaluation() -> None:
    bars = [
        bar("2024-01-02T00:00:00", 1.1000, 1.1020),
        bar("2024-01-03T00:00:00", 1.1050, 1.1030),
        bar("2024-01-04T00:00:00", 1.1040, 1.1060),
    ]
    signal = GapContinuationSignal()
    signal(bars, 2)
    try:
        signal(bars, 1)
    except ValueError as exc:
        assert "chronologically" in str(exc)
    else:
        raise AssertionError("expected chronological evaluation error")
