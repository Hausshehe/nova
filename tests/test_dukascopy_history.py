from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_research.dukascopy_history import (
    Candle,
    _decode_candle_file,
    _deduplicate_and_validate,
    _native_url,
    _request_bytes,
)


class FakeResponse:
    def __init__(self, status_code, content, headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.text = content.decode("utf-8", errors="replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, timeout, headers):
        self.calls.append((url, timeout, headers))
        return self.responses.pop(0)


def test_native_url():
    assert _native_url("EURUSD", "1D", 2024).endswith(
        "/datafeed/EURUSD/2024/BID_candles_day_1.bi5"
    )


def test_decode_candle_file():
    import struct

    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    payload = b"".join(
        struct.pack(">IIffff", *row)
        for row in [
            (0, 100, 110, 90, 105, 2.5),
            (3600, 105, 120, 100, 115, 3.0),
        ]
    )
    candles = _decode_candle_file(payload, base)
    assert candles == [
        Candle("2024-01-01T00:00:00+00:00", 100.0, 110.0, 90.0, 105.0, 2.5),
        Candle("2024-01-01T01:00:00+00:00", 105.0, 120.0, 100.0, 115.0, 3.0),
    ]


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
        FakeResponse(429, b"", {"Retry-After": "2"}),
        FakeResponse(200, b"ok"),
    ])
    assert _request_bytes(session, "https://example.test") == b"ok"
    assert sleeps == [2.0]
