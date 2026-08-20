from datetime import datetime, timezone

from trading_research.data import Bar
from trading_research.dukascopy_history import Candle, _deduplicate_and_validate


def test_recovery_validator_accepts_normalized_bar_objects() -> None:
    bars = [
        Bar(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=100.0,
            high=110.0,
            low=90.0,
            close=105.0,
            volume=1.0,
        ),
        Bar(
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            open=105.0,
            high=115.0,
            low=100.0,
            close=110.0,
            volume=2.0,
        ),
    ]

    assert bars[0].timestamp_utc == "2024-01-01T00:00:00+00:00"
    validated = _deduplicate_and_validate(bars)

    assert validated == bars


def test_recovery_validator_preserves_native_candle_behavior() -> None:
    candles = [
        Candle(
            timestamp_utc="2024-01-01T00:00:00+00:00",
            open=100.0,
            high=110.0,
            low=90.0,
            close=105.0,
            volume=1.0,
        ),
        Candle(
            timestamp_utc="2024-01-01T01:00:00+00:00",
            open=105.0,
            high=115.0,
            low=100.0,
            close=110.0,
            volume=2.0,
        ),
    ]

    validated = _deduplicate_and_validate(candles)

    assert validated == candles
