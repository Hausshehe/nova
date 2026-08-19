from __future__ import annotations

import lzma
from datetime import datetime, timezone

import requests

from trading_research.dukascopy_history import (
    CANDLE_STRUCT,
    DATAFEED_BASE_URL,
    DukascopyClient,
    INSTRUMENTS,
    _aggregate_4h,
    _decode_candle_file,
    _native_url,
    _request_bytes,
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
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


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
    assert _native_url("WTI", "1H", 2024, 1).endswith(
        "/LIGHTCMDUSD/2024/00/BID_candles_hour_1.bi5"
    )


def test_native_candle_decoder():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    payload = _compressed_rows([
        (0, 100, 110, 90, 105, 2.5),
        (3600, 105, 120, 100, 115, 3.0),
    ])
    candles = _decode_candle_file(payload, base)
    assert candles == [
        Candle("2024-01-01T00:00:00+00:00", 100.0, 110.0, 90.0, 105.0, 2.5),
        Candle("2024-01-01T01:00:00+00:00", 105.0, 120.0, 100.0, 115.0, 3.0),
    ]


def test_request_bytes_retries_429_and_honors_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr("trading_research.dukascopy_history.time.sleep", sleeps.append)
    session = FakeSession([
        FakeResponse(429, b""),
        FakeResponse(200, b"payload"),
    ])
    session.responses[0].headers["Retry-After"] = "3"
    payload = _request_bytes(session, "https://example.test/file.bi5")
    assert payload == b"payload"
    assert len(session.calls) == 2
    assert sleeps == [3.0]


def test_request_bytes_retries_transient_connect_timeout(monkeypatch):
    sleeps = []
    monkeypatch.setattr("trading_research.dukascopy_history.time.sleep", sleeps.append)
    session = FakeSession([
        requests.exceptions.ConnectTimeout("timed out"),
        FakeResponse(200, b"payload"),
    ])
    payload = _request_bytes(session, "https://example.test/file.bi5")
    assert payload == b"payload"
    assert len(session.calls) == 2
    assert sleeps == [2.0]


def test_aggregate_4h_uses_only_complete_utc_buckets():
    rows = [
        Candle("2024-01-01T00:00:00+00:00", 10, 12, 9, 11, 1),
        Candle("2024-01-01T01:00:00+00:00", 11, 13, 10, 12, 2),
        Candle("2024-01-01T02:00:00+00:00", 12, 14, 11, 13, 3),
        Candle("2024-01-01T03:00:00+00:00", 13, 15, 12, 14, 4),
        Candle("2024-01-01T05:00:00+00:00", 14, 16, 13, 15, 5),
    ]
    result = _aggregate_4h(rows)
    assert result == [Candle("2024-01-01T00:00:00+00:00", 10, 15, 9, 14, 10)]


def test_universe_is_exactly_frozen():
    assert len(INSTRUMENTS) == 13
    assert set(INSTRUMENTS) == {
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
        "US500", "NAS100", "US30", "XAUUSD", "XAGUSD", "WTI",
    }
