from datetime import datetime, timezone

import pytest

from trading_research.data import Bar, load_csv, validate_ohlcv_rows


def _row(timestamp: str, close: str = "100") -> dict[str, str]:
    return {
        "timestamp": timestamp,
        "open": "99",
        "high": "101",
        "low": "98",
        "close": close,
        "volume": "1",
    }


def test_validate_rows_rejects_duplicate_timestamps():
    rows = [
        _row("2026-01-01T00:00:00Z"),
        _row("2026-01-01T00:00:00Z"),
    ]
    report = validate_ohlcv_rows(rows)
    assert not report.ok
    assert "timestamps_not_strictly_increasing" in report.reasons[0]


def test_bar_rejects_infinite_numeric_values():
    bar = Bar(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        open=99.0,
        high=float("inf"),
        low=98.0,
        close=100.0,
        volume=1.0,
    )
    with pytest.raises(ValueError, match="non-finite"):
        bar.validate()


def test_load_csv_rejects_duplicate_timestamps(tmp_path):
    path = tmp_path / "bars.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-01-01T00:00:00Z,99,101,98,100,1\n"
        "2026-01-01T00:00:00Z,99,101,98,100,1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        load_csv(path)
