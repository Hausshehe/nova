from datetime import datetime, timezone

from trading_research.data import Bar
from trading_research.friday_continuation import FridayContinuationSignal


def bar(timestamp: str, close: float, *, open_: float | None = None) -> Bar:
    return Bar(
        timestamp=datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
        open=open_ if open_ is not None else close,
        high=close,
        low=close,
        close=close,
        volume=100.0,
    )


def test_positive_friday_requests_long_until_next_trading_bar() -> None:
    bars = [
        bar("2024-01-04T00:00:00", 1.1000),  # Thu
        bar("2024-01-05T00:00:00", 1.1100),  # Fri: positive
        bar("2024-01-08T00:00:00", 1.1120),  # Mon
        bar("2024-01-09T00:00:00", 1.1130),  # Tue
    ]
    signal = FridayContinuationSignal()
    assert signal(bars, 0) is False
    assert signal(bars, 1) is True
    assert signal(bars, 2) is False


def test_negative_friday_does_not_open() -> None:
    bars = [
        bar("2024-01-04T00:00:00", 1.1100),
        bar("2024-01-05T00:00:00", 1.1000),
        bar("2024-01-08T00:00:00", 1.1010),
    ]
    signal = FridayContinuationSignal()
    assert signal(bars, 1) is False
    assert signal(bars, 2) is False


def test_signal_requires_chronological_evaluation() -> None:
    bars = [
        bar("2024-01-04T00:00:00", 1.10),
        bar("2024-01-05T00:00:00", 1.11),
        bar("2024-01-08T00:00:00", 1.12),
    ]
    signal = FridayContinuationSignal()
    signal(bars, 2)
    try:
        signal(bars, 1)
    except ValueError as exc:
        assert "chronologically" in str(exc)
    else:
        raise AssertionError("expected chronological evaluation error")
