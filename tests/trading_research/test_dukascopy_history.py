from datetime import datetime, timezone

import pytest

from trading_research.dukascopy_history import (
    Candle,
    DukascopyClient,
    _aggregate_4h,
    _deduplicate_and_validate,
    _native_url,
    write_csv,
)


def candle(hour: int, *, open_: float = 1, high: float = 2, low: float = 0, close: float = 1) -> Candle:
    return Candle(
        timestamp_utc=datetime(2020, 1, 1, hour, tzinfo=timezone.utc).isoformat(),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1,
    )


def test_native_urls_use_frozen_feed_symbols():
    assert _native_url("EURUSD", "1D", 2020).endswith("/EURUSD/2020/BID_candles_day_1.bi5")
    assert _native_url("US500", "1D", 2020).endswith("/USA500IDXUSD/2020/BID_candles_day_1.bi5")
    assert _native_url("XAUUSD", "1H", 2020, 1).endswith("/XAUUSD/2020/00/BID_candles_hour_1.bi5")


def test_deduplicate_and_validate_sorts_and_rejects_invalid_ohlc():
    rows = [candle(1), candle(0)]
    ordered = _deduplicate_and_validate(rows)
    assert [row.timestamp_utc for row in ordered] == [candle(0).timestamp_utc, candle(1).timestamp_utc]

    with pytest.raises(ValueError, match="candle_ohlc_invalid"):
        _deduplicate_and_validate([candle(0, open_=3)])


def test_deduplicate_and_validate_keeps_one_row_per_timestamp():
    first = candle(0, close=1)
    replacement = candle(0, close=1.5)
    result = _deduplicate_and_validate([first, replacement])
    assert len(result) == 1
    assert result[0].close == 1.5


def test_aggregate_4h_requires_complete_four_hour_bucket():
    rows = [candle(hour) for hour in range(4)]
    result = _aggregate_4h(rows)
    assert len(result) == 1
    assert result[0].timestamp_utc == "2020-01-01T00:00:00+00:00"
    assert result[0].open == 1
    assert result[0].high == 2
    assert result[0].low == 0
    assert result[0].close == 1
    assert result[0].volume == 4


def test_aggregate_4h_drops_incomplete_bucket():
    assert _aggregate_4h([candle(0), candle(1), candle(2)]) == []


def test_client_rejects_unknown_instrument_and_bad_time_range():
    client = DukascopyClient()
    with pytest.raises(ValueError, match="unsupported_instrument"):
        client.historical_prices(
            instrument="NOTREAL",
            timeframe="1D",
            start_utc="2020-01-01T00:00:00+00:00",
            end_utc="2020-01-02T00:00:00+00:00",
        )
    with pytest.raises(ValueError, match="end_must_be_after_start"):
        client.historical_prices(
            instrument="EURUSD",
            timeframe="1D",
            start_utc="2020-01-02T00:00:00+00:00",
            end_utc="2020-01-01T00:00:00+00:00",
        )


def test_write_csv_produces_stable_hash(tmp_path):
    rows = [candle(0)]
    first = write_csv(rows, tmp_path / "a.csv")
    second = write_csv(rows, tmp_path / "b.csv")
    assert first == second
