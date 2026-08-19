from __future__ import annotations

import pytest
import requests

from trading_research.dukascopy_history import (
    BASE_URL,
    INSTRUMENTS_FALLBACK_URL,
    DukascopyClient,
)


class FakeResponse:
    def __init__(self, status_code: int, payload, headers=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text if text is not None else ""

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} error")
            error.response = self
            raise error

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def test_uses_documented_dukascopy_api_endpoint():
    assert BASE_URL == "https://freeserv.dukascopy.com/2.0/"


def test_instrument_fallback_endpoint_is_distinct():
    assert INSTRUMENTS_FALLBACK_URL == "https://freeserv.dukascopy.com/2.0/index.php"


def test_get_retries_429_and_honors_retry_after(monkeypatch):
    session = FakeSession([
        FakeResponse(429, {"error": "rate limited"}, {"Retry-After": "3"}),
        FakeResponse(200, [{"id": 1, "name": "EUR/USD"}]),
    ])
    sleeps = []
    monkeypatch.setattr("trading_research.dukascopy_history.time.sleep", sleeps.append)

    client = DukascopyClient(session=session)
    result = client._get({"path": "api/instrumentList"})

    assert result == [{"id": 1, "name": "EUR/USD"}]
    assert len(session.calls) == 2
    assert sleeps == [3.0]
    assert session.calls[0][0][0] == BASE_URL
    assert session.calls[0][1]["headers"]["Referer"] == "https://freeserv.dukascopy.com/"
    assert session.calls[0][1]["headers"]["Accept"] == "application/json, text/plain, */*"


def test_get_raises_non_429_without_retry():
    session = FakeSession([FakeResponse(500, {"error": "server"})])
    client = DukascopyClient(session=session)

    with pytest.raises(requests.HTTPError):
        client._get({"path": "api/instrumentList"})

    assert len(session.calls) == 1


def test_get_reports_invalid_json_response():
    response = FakeResponse(
        200,
        None,
        {"Content-Type": "text/html"},
        "<html>temporarily unavailable</html>",
    )
    response.json = lambda: (_ for _ in ()).throw(
        requests.exceptions.JSONDecodeError("Expecting value", "", 0)
    )
    client = DukascopyClient(session=FakeSession([response]))

    with pytest.raises(ValueError, match="dukascopy_invalid_json:status=200:content_type=text/html"):
        client._get({"path": "api/instrumentList"})


def test_resolve_instruments_falls_back_after_204():
    primary = FakeResponse(204, None, {"Content-Type": "text/javascript; charset=UTF-8"}, "")
    primary.json = lambda: (_ for _ in ()).throw(
        requests.exceptions.JSONDecodeError("Expecting value", "", 0)
    )
    fallback_payload = [
        {"id": 1, "name": "EUR/USD"},
        {"id": 2, "name": "GBP/USD"},
        {"id": 3, "name": "USD/JPY"},
        {"id": 4, "name": "AUD/USD"},
        {"id": 5, "name": "USD/CAD"},
        {"id": 6, "name": "USD/CHF"},
        {"id": 7, "name": "NZD/USD"},
        {"id": 8, "name": "US500"},
        {"id": 9, "name": "NAS100"},
        {"id": 10, "name": "US30"},
        {"id": 11, "name": "XAU/USD"},
        {"id": 12, "name": "XAG/USD"},
        {"id": 13, "name": "WTI"},
    ]
    session = FakeSession([primary, FakeResponse(200, fallback_payload)])

    result = DukascopyClient(session=session).resolve_instruments()

    assert set(result) == {
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
        "US500", "NAS100", "US30", "XAUUSD", "XAGUSD", "WTI",
    }
    assert session.calls[0][0][0] == BASE_URL
    assert session.calls[1][0][0] == INSTRUMENTS_FALLBACK_URL
    assert session.calls[1][1]["params"] == {"path": "common/instruments"}


def test_resolve_instruments_parses_nested_fallback_payload():
    primary = FakeResponse(204, None, {"Content-Type": "text/javascript"}, "")
    primary.json = lambda: (_ for _ in ()).throw(
        requests.exceptions.JSONDecodeError("Expecting value", "", 0)
    )
    nested = {
        "groups": [{
            "instruments": [
                {"id": 1, "symbol": "EUR/USD"},
                {"id": 2, "symbol": "GBP/USD"},
                {"id": 3, "symbol": "USD/JPY"},
                {"id": 4, "symbol": "AUD/USD"},
                {"id": 5, "symbol": "USD/CAD"},
                {"id": 6, "symbol": "USD/CHF"},
                {"id": 7, "symbol": "NZD/USD"},
                {"id": 8, "symbol": "US500"},
                {"id": 9, "symbol": "NAS100"},
                {"id": 10, "symbol": "US30"},
                {"id": 11, "symbol": "XAU/USD"},
                {"id": 12, "symbol": "XAG/USD"},
                {"id": 13, "symbol": "WTI"},
            ]
        }]
    }
    session = FakeSession([primary, FakeResponse(200, nested)])

    result = DukascopyClient(session=session).resolve_instruments()

    assert result["EURUSD"] == 1
    assert result["XAUUSD"] == 11
    assert result["WTI"] == 13
