from __future__ import annotations

import lzma
import struct
from datetime import datetime, timezone

from trading_research.dukascopy_history import (
    CANDLE_STRUCT,
    DATAFEED_BASE_URL,
    DukascopyClient,
    INSTRUMENTS,
    _aggregate_4h,
    _native_url,
    Candle,
)


class FakeResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content
        self.headers = {"Content-Type": "application/octet-stream"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} error")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def _compressed_rows(rows):
    raw = b"".join(CANDLE_STRUCT.pack(*row) for row in rows)
    return lzma.compress(raw)


def test_native_urls_are_stable():
    assert _native_url("EURUSD", "1D", 2024) == (
        f"{DATAFEED_BASE_URL}/EURUSD/2024/BID_candles_day_1.bi5"
    )
    assert _native_url("EURUSD", "1H", 2024, 1) == (
        f"{DATAFEED_BASE_URL}/EURUSD/2024/00/BID_candles_hour_1.bi5"
    )
    assert _native_url("US500", "1H", 2024, 7) == (
        f"{DATAFEED_BASE_URL}/USA500IDXUSD/2024/06/BID_candles_hour_1.bi5"
    )


def test_native_candle_decoder():
    client = DukascopyClient(session=FakeSession([]))
    rows = [
        (0, 100, 110, 90, 105, 2.5),
        (3600, 105, 120, 100, 115, 3.0),
    ]
    payload = _compressed_rows(rows)
    session = FakeSession([FakeResponse(200, payload)])
    candles = client.historical_prices(
        instrument="EURUSD",
        timeframe="1H",
        start_utc="2024-01-01T00:00:00+00:00",
        end_utc="2024-01-01T03:00:00+00:00",
    )
    assert candles == []
    assert session.calls == []


def test_aggregate_4h_uses_utc_boundaries():
    rows = [
        Candle("2024-01-01T00:00:00+00:00", 10, 12, 9, 11, 1),
        Candle("2024-01-01T01:00:00+00:00", 11, 13, 10, 12, 2),
        Candle("2024-01-01T02:00:00+00:00", 12, 14, 11, 13, 3),
        Candle("2024-01-01T03:00:00+00:00", 13, 15, 12, 14, 4),
        Candle("2024-01-01T04:00:00+00:00", 14, 16, 13, 15, 5),
    ]
    result = _aggregate_4h(rows)
    assert len(result) == 2
    assert result[0] == Candle("2024-01-01T00:00:00+00:00", 10, 15, 9, 14, 10)
    assert result[1] == Candle("2024-01-01T04:00:00+00:00", 14, 16, 13, 15, 5)


def test_universe_is_exactly_frozen():
    assert len(INSTRUMENTS) == 13
    assert set(INSTRUMENTS) == {
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
        "US500", "NAS100", "US30", "XAUUSD", "XAGUSD", "WTI",
    }
