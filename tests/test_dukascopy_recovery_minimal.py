from __future__ import annotations

import csv
import hashlib
import lzma
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_research.dukascopy_history import (
    CANDLE_STRUCT,
    DATAFEED_BASE_URL,
    INSTRUMENTS,
    TIMEFRAMES,
    WTI_DUAL_DIRECTORY_YEAR,
    WTI_LEGACY_DATAFEED,
    _decode_candle_file,
    _feed_symbols_for_period,
    _native_url,
    Candle,
)
from trading_research.migrate_legacy_broader_artifacts import (
    LEGACY_SOURCE_RUN_ID,
    LEGACY_WTI_4H_DATASET,
    invalidate_legacy_wti_4h,
)
from trading_research.rebuild_recovery_manifest import rebuild_manifest


def _compressed(rows: list[tuple[int, int, int, int, int, float]]) -> bytes:
    return lzma.compress(b"".join(CANDLE_STRUCT.pack(*row) for row in rows))


def test_native_decoder_preserves_dukascopy_open_close_low_high_layout() -> None:
    candles = _decode_candle_file(
        _compressed([(0, 79840, 81690, 79700, 81730, 1.0)]),
        datetime(2010, 10, 1, tzinfo=timezone.utc),
    )
    assert candles == [
        Candle("2010-10-01T00:00:00+00:00", 79840.0, 81730.0, 79700.0, 81690.0, 1.0)
    ]


def test_wti_historical_directory_resolution() -> None:
    assert _feed_symbols_for_period("WTI", 2013) == (WTI_LEGACY_DATAFEED,)
    assert _feed_symbols_for_period("WTI", WTI_DUAL_DIRECTORY_YEAR) == (
        WTI_LEGACY_DATAFEED,
        "LIGHTCMDUSD",
    )
    assert _feed_symbols_for_period("WTI", 2015) == ("LIGHTCMDUSD",)
    assert _feed_symbols_for_period("EURUSD", 2014) == ("EURUSD",)

    assert _native_url(
        "WTI", "1D", 2013, feed_symbol=WTI_LEGACY_DATAFEED
    ) == f"{DATAFEED_BASE_URL}/WTICMDUSD/2013/BID_candles_day_1.bi5"
    assert _native_url(
        "WTI", "1H", 2015, 1, feed_symbol="LIGHTCMDUSD"
    ) == f"{DATAFEED_BASE_URL}/LIGHTCMDUSD/2015/00/BID_candles_hour_1.bi5"


def test_duplicate_timestamp_conflicts_fail_closed() -> None:
    from trading_research.dukascopy_history import _deduplicate_and_validate

    rows = [
        Candle("2024-01-01T00:00:00+00:00", 100, 110, 90, 105, 1),
        Candle("2024-01-01T00:00:00+00:00", 100, 111, 90, 105, 1),
    ]
    with pytest.raises(ValueError, match="duplicate_timestamp_conflict"):
        _deduplicate_and_validate(rows)


def test_invalidate_legacy_wti_4h_exact_source(tmp_path: Path) -> None:
    target = tmp_path / LEGACY_WTI_4H_DATASET
    target.write_text("legacy", encoding="utf-8")
    removed = invalidate_legacy_wti_4h(tmp_path, source_run_id=LEGACY_SOURCE_RUN_ID)
    assert removed == LEGACY_WTI_4H_DATASET
    assert not target.exists()


def _write_dataset(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for index in range(100):
            ts = start + timedelta(hours=index)
            writer.writerow([ts.isoformat(), "1", "2", "1", "2", "1"])


def test_rebuild_recovery_manifest_creates_exact_26_entries(tmp_path: Path) -> None:
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            _write_dataset(tmp_path / f"{instrument}_{timeframe}.csv")

    manifests = rebuild_manifest(tmp_path)

    assert len(manifests) == 26
    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.is_file()
    sample = tmp_path / "EURUSD_1D.csv"
    expected_hash = hashlib.sha256(sample.read_bytes()).hexdigest()
    assert any(item.instrument == "EURUSD" and item.timeframe == "1D" and item.sha256 == expected_hash for item in manifests)


def test_rebuild_recovery_manifest_does_not_write_partial_manifest(tmp_path: Path) -> None:
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            _write_dataset(tmp_path / f"{instrument}_{timeframe}.csv")
    (tmp_path / "WTI_4H.csv").unlink()

    with pytest.raises(ValueError, match="dataset_missing:WTI_4H.csv"):
        rebuild_manifest(tmp_path)

    assert not (tmp_path / "manifest.json").exists()
