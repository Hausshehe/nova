from trading_research.yahoo_history import fetch_wti_1d


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def test_yahoo_wti_normalizes_exchange_timestamp_and_validates_ohlc():
    session = FakeSession(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [1285894800],  # 2010-10-01 05:00 UTC
                        "indicators": {
                            "quote": [
                                {
                                    "open": [79.83999633789062],
                                    "high": [81.69000244140625],
                                    "low": [79.69999694824219],
                                    "close": [81.58000183105469],
                                    "volume": [359944],
                                }
                            ]
                        },
                    }
                ]
            }
        }
    )

    rows = fetch_wti_1d(
        start_utc="2010-10-01T00:00:00+00:00",
        end_utc="2010-10-02T00:00:00+00:00",
        session=session,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.timestamp_utc == "2010-10-01T00:00:00+00:00"
    assert row.open == 79.83999633789062
    assert row.high == 81.69000244140625
    assert row.low == 79.69999694824219
    assert row.close == 81.58000183105469
    assert row.volume == 359944.0


def test_yahoo_wti_rejects_invalid_ohlc():
    session = FakeSession(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [1285894800],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [79.84],
                                    "high": [81.69],
                                    "low": [79.70],
                                    "close": [81.73],
                                    "volume": [1],
                                }
                            ]
                        },
                    }
                ]
            }
        }
    )

    try:
        fetch_wti_1d(
            start_utc="2010-10-01T00:00:00+00:00",
            end_utc="2010-10-02T00:00:00+00:00",
            session=session,
        )
    except ValueError as exc:
        assert str(exc).startswith("candle_ohlc_invalid:")
    else:
        raise AssertionError("invalid OHLC must be rejected")
