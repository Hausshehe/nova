from trading_research.dukascopy_history import DukascopyClient, normalize_candles, write_csv


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append(params)
        start = int(params["start"])
        if len(self.calls) == 1:
            rows = []
            for index in range(5000):
                rows.append({"timestamp": start + index, "open": 1, "high": 2, "low": 0, "close": 1, "volume": 1})
            return FakeResponse(rows)
        return FakeResponse([
            {"timestamp": start, "open": 1, "high": 2, "low": 0, "close": 1, "volume": 1},
        ])


def test_normalize_sorts_and_normalizes_timestamps():
    # Unambiguous 2020-era millisecond timestamps (> 1e12).
    candles = normalize_candles([
        {"timestamp": 1609459200000, "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 10},
        {"timestamp": 1577836800000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 5},
    ])
    assert candles[0].timestamp_utc == "2020-01-01T00:00:00+00:00"
    assert candles[1].timestamp_utc == "2021-01-01T00:00:00+00:00"


def test_normalize_rejects_invalid_ohlc():
    try:
        normalize_candles([{"timestamp": 1000, "open": 5, "high": 3, "low": 1, "close": 2, "volume": 1}])
    except ValueError as exc:
        assert str(exc) == "candle_ohlc_invalid"
    else:
        raise AssertionError("invalid OHLC was accepted")


def test_normalize_rejects_duplicate_timestamps():
    try:
        normalize_candles([
            {"timestamp": 1000, "open": 1, "high": 2, "low": 0, "close": 1, "volume": 1},
            {"timestamp": 1000, "open": 1, "high": 2, "low": 0, "close": 1, "volume": 1},
        ])
    except ValueError as exc:
        assert str(exc) == "candle_timestamps_not_strictly_increasing"
    else:
        raise AssertionError("duplicate timestamps were accepted")


def test_pagination_fetches_more_than_one_page():
    session = FakeSession()
    client = DukascopyClient(session=session)
    rows = client.historical_prices(
        instrument_id=1,
        timeframe="4H",
        start_utc="2020-01-01T00:00:00+00:00",
        end_utc="2030-01-01T00:00:00+00:00",
    )
    assert len(session.calls) == 2
    assert len(rows) == 5001
    assert session.calls[1]["start"] > session.calls[0]["start"]


def test_write_csv_produces_stable_hash(tmp_path):
    candles = normalize_candles([
        {"timestamp": 1000, "open": 1, "high": 2, "low": 0, "close": 1, "volume": 1},
    ])
    first = write_csv(candles, tmp_path / "a.csv")
    second = write_csv(candles, tmp_path / "b.csv")
    assert first == second
