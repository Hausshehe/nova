from __future__ import annotations

import csv
import hashlib
import json
import lzma
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
    Candle,
    _decode_candle_file,
    _deduplicate_and_validate,
    _feed_symbols_for_period,
    _native_url,
)
from trading_research.migrate_legacy_broader_artifacts import (
    LEGACY_SOURCE_RUN_ID,
    LEGACY_WTI_4H_DATASET,
    invalidate_legacy_wti_4h,
)
from trading_research.rebuild_recovery_manifest import rebuild_manifest


def _compressed(rows: list[tuple[int, int, int, int, int, float]]) -> bytes:
    return lzma.compress(b"".join(CANDLE_STRUCT.pack(*row) for row in rows))


def test_wti_directory_resolution_is_explicit() -> None:
    assert _feed_symbols_for_period("WTI", 2013) == (WTI_LEGACY_DATAFEED,)
    assert _feed_symbols_for_period("WTI", WTI_DUAL_DIRECTORY_YEAR) == (WTI_LEGACY_DATAFEED, "LIGHTCMDUSD")
    assert _feed_symbols_for_period("WTI", 2015) == ("LIGHTCMDUSD",)
    assert _feed_symbols_for_period("EURUSD", 2014) == ("EURUSD",)
    assert _native_url("WTI", "1D", 2013, feed_symbol=WTI_LEGACY_DATAFEED) == (
        f"{DATAFEED_BASE_URL}/WTICMDUSD/2013/BID_candles_day_1.bi5"
    )


def test_native_decoder_remains_frozen_layout() -> None:
    candles = _decode_candle_file(
        _compressed([(0, 79840, 81690, 79700, 81730, 1.0)]),
        datetime(2010, 10, 1, tzinfo=timezone.utc),
    )
    assert candles == [
        Candle("2010-10-01T00:00:00+00:00", 79840.0, 81730.0, 79700.0, 81690.0, 1.0)
    ]


def test_duplicate_conflict_guard_is_opt_in() -> None:
    rows = [
        Candle("2024-01-01T00:00:00+00:00", 100, 110, 90, 105, 1),
        Candle("2024-01-01T00:00:00+00:00", 100, 111, 90, 105, 1),
    ]
    result = _deduplicate_and_validate(rows)
    assert result[-1].high == 111
    with pytest.raises(ValueError, match="duplicate_timestamp_conflict"):
        _deduplicate_and_validate(rows, reject_duplicate_conflicts=True)


def test_invalidate_legacy_wti_4h_requires_exact_source(tmp_path: Path) -> None:
    target = tmp_path / LEGACY_WTI_4H_DATASET
    target.write_text("legacy", encoding="utf-8")
    assert invalidate_legacy_wti_4h(tmp_path, source_run_id=LEGACY_SOURCE_RUN_ID) == LEGACY_WTI_4H_DATASET
    assert not target.exists()

    target.write_text("legacy", encoding="utf-8")
    with pytest.raises(ValueError, match="legacy_migration_source_run_mismatch"):
        invalidate_legacy_wti_4h(tmp_path, source_run_id="other")
    assert target.exists()


def _write_dataset(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for index in range(100):
            ts = start + timedelta(hours=index)
            writer.writerow([ts.isoformat(), "1", "2", "1", "2", "1"])


def test_recovery_manifest_is_complete_and_hashed(tmp_path: Path) -> None:
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            _write_dataset(tmp_path / f"{instrument}_{timeframe}.csv")
    manifests = rebuild_manifest(tmp_path)
    assert len(manifests) == 26
    sample = tmp_path / "EURUSD_1D.csv"
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    assert next(item for item in manifests if item.instrument == "EURUSD" and item.timeframe == "1D").sha256 == digest
    assert (tmp_path / "manifest.json").is_file()


def test_recovery_manifest_rejects_invalid_ohlc_before_write(tmp_path: Path) -> None:
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            _write_dataset(tmp_path / f"{instrument}_{timeframe}.csv")
    broken = tmp_path / "WTI_1D.csv"
    rows = list(csv.reader(broken.open("r", encoding="utf-8")))
    rows[1][2] = "0"  # high < open: invalid OHLC
    with broken.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rows)
    with pytest.raises(ValueError, match="candle_ohlc_invalid"):
        rebuild_manifest(tmp_path)
    assert not (tmp_path / "manifest.json").exists()


def test_recovery_manifest_fails_before_partial_write(tmp_path: Path) -> None:
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            _write_dataset(tmp_path / f"{instrument}_{timeframe}.csv")
    existing_manifest = tmp_path / "manifest.json"
    existing_manifest.write_text(json.dumps({"sentinel": True}), encoding="utf-8")
    (tmp_path / "WTI_4H.csv").unlink()
    with pytest.raises(ValueError, match="dataset_missing:WTI_4H.csv"):
        rebuild_manifest(tmp_path)
    assert json.loads(existing_manifest.read_text(encoding="utf-8")) == {"sentinel": True}
