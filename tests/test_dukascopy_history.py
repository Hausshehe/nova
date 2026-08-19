from __future__ import annotations

import json

import pytest
import requests

from trading_research.dukascopy_history import DukascopyClient


class FakeResponse:
    def __init__(self, status_code: int, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

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
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


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
    assert session.calls == 2
    assert sleeps == [3.0]


def test_get_raises_non_429_without_retry():
    session = FakeSession([FakeResponse(500, {"error": "server"})])
    client = DukascopyClient(session=session)

    with pytest.raises(requests.HTTPError):
        client._get({"path": "api/instrumentList"})

    assert session.calls == 1
