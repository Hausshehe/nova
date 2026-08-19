from trading_research.dukascopy_history import normalize_candles, write_csv


def test_normalize_sorts_and_normalizes_timestamps():
    candles = normalize_candles([
        {"timestamp": 2000, "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 10},
        {"timestamp": 1000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 5},
    ])
    assert candles[0].timestamp_utc == "1970-01-01T00:00:01+00:00"
    assert candles[1].timestamp_utc == "1970-01-01T00:00:02+00:00"


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


def test_write_csv_produces_stable_hash(tmp_path):
    candles = normalize_candles([
        {"timestamp": 1000, "open": 1, "high": 2, "low": 0, "close": 1, "volume": 1},
    ])
    first = write_csv(candles, tmp_path / "a.csv")
    second = write_csv(candles, tmp_path / "b.csv")
    assert first == second
