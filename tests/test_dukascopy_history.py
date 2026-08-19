from __future__ import annotations

import lzma
from datetime import datetime, timezone

import pytest
import requests

from trading_research.dukascopy_history import (
    CANDLE_STRUCT,
    DATAFEED_BASE_URL,
    DukascopyClient,
    INSTRUMENTS,
    WTI_LEGACY_DATAFEED,
    WTI_SYMBOL_SWITCH_YEAR,
    _aggregate_4h,
    _decode_candle_file,
    _deduplicate_and_validate,
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


def test_wti_daily_uses_legacy_directory_before_symbol_switch():
    assert WTI_LEGACY_DATAFEED == "WTICMDUSD"
    assert WTI_SYMBOL_SWITCH_YEAR == 2015
    assert _native_url("WTI", "1D", 2014) == (
        f"{DATAFEED_BASE_URL}/WTICMDUSD/2014/BID_candles_day_1.bi5"
    )
    assert _native_url("WTI", "1D", 2015) == (
        f"{DATAFEED_BASE_URL}/LIGHTCMDUSD/2015/BID_candles_day_1.bi5"
    )


def test_native_candle_decoder_preserves_open_high_low_close_order():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # Dukascopy native candle records are seconds, open, high, low, close, volume.
    payload = _compressed_rows([
        (0, 100, 110, 90, 105, 2.5),
        (3600, 105, 120, 100, 115, 3.0),
    ])
    candles = _decode_candle_file(payload, base)
    assert candles == [
        Candle("2024-01-01T00:00:00+00:00", 100.0, 110.0, 90.0, 105.0, 2.5),
        Candle("2024-01-01T01:00:00+00:00", 105.0, 120.0, 100.0, 115.0, 3.0),
    ]


def test_native_candle_decoder_does_not_swap_high_and_close():
    payload = _compressed_rows([(0, 79840, 81730, 79700, 81690, 1.0)])
    candles = _decode_candle_file(payload, datetime(2010, 10, 1, tzinfo=timezone.utc))
    assert candles == [
        Candle("2010-10-01T00:00:00+00:00", 79840.0, 81730.0, 79700.0, 81690.0, 1.0)
    ]
    assert candles[0].low <= candles[0].close <= candles[0].high


def test_validation_rejects_invalid_first_and_middle_rows():
    rows = [
        Candle("2024-01-01T00:00:00+00:00", 120, 110, 90, 100, 1),
        Candle("2024-01-01T01:00:00+00:00", 100, 110, 90, 105, 1),
    ]
    with pytest.raises(ValueError, match=r"candle_ohlc_invalid:timestamp=2024-01-01T00:00:00\+00:00"):
        _deduplicate_and_validate(rows)

    rows = [
        Candle("2024-01-01T00:00:00+00:00", 100, 110, 90, 105, 1),
        Candle("2024-01-01T01:00:00+00:00", 120, 110, 90, 100, 1),
    ]
    with pytest.raises(ValueError, match=r"candle_ohlc_invalid:timestamp=2024-01-01T01:00:00\+00:00"):
        _deduplicate_and_validate(rows)


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


def test_request_bytes_retries_transient_503(monkeypatch):
    sleeps = []
    monkeypatch.setattr("trading_research.dukascopy_history.time.sleep", sleeps.append)
    session = FakeSession([
        FakeResponse(503, b""),
        FakeResponse(503, b""),
        FakeResponse(200, b"payload"),
    ])
    payload = _request_bytes(session, "https://example.test/file.bi5")
    assert payload == b"payload"
    assert len(session.calls) == 3
    assert sleeps == [2.0, 4.0]


def test_historical_prices_reports_progress(monkeypatch):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    payload = _compressed_rows([(0, 100, 110, 90, 105, 1.0)])
    session = FakeSession([FakeResponse(200, payload)])
    messages = []
    client = DukascopyClient(session=session)
    candles = client.historical_prices(
        instrument="EURUSD",
        timeframe="1D",
        start_utc="2024-01-01T00:00:00+00:00",
        end_utc="2024-01-02T00:00:00+00:00",
        progress=messages.append,
    )
    assert candles[0].timestamp_utc == base.isoformat()
    assert messages == [
        "request EURUSD 1D 2024",
        "received EURUSD 1D 2024: bars=1",
        "validated EURUSD 1D: bars=1",
    ]


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
