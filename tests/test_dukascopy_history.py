from __future__ import annotations

import pytest
import requests

from trading_research.dukascopy_history import BASE_URL, DukascopyClient


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
