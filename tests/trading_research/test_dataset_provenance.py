from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_research.dataset_provenance import build_manifest, verify_manifest, write_manifest


def _write_csv(path: Path) -> None:
    start = datetime(2023, 1, 2, tzinfo=timezone.utc)
    lines = ["timestamp,open,high,low,close,volume"]
    for i in range(10):
        ts = start + timedelta(days=i)
        value = 1.0 + i * 0.001
        lines.append(f"{ts.isoformat()},{value},{value},{value},{value},1")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_build_manifest_records_frozen_provenance(tmp_path: Path) -> None:
    dataset = tmp_path / "eurusd.csv"
    manifest_path = tmp_path / "eurusd.manifest.json"
    _write_csv(dataset)

    manifest = build_manifest(
        dataset,
        source_name="Dukascopy Historical Data Export",
        source_url="https://www.dukascopy.com/swiss/english/marketwatch/historical/",
        instrument="EURUSD",
        timeframe="1D",
        retrieved_at_utc="2026-08-19T12:00:00+00:00",
    )
    write_manifest(manifest, manifest_path)

    assert manifest.rows == 10
    assert manifest.instrument == "EURUSD"
    verify_manifest(manifest, dataset)
    assert manifest_path.exists()


def test_manifest_detects_byte_tampering(tmp_path: Path) -> None:
    dataset = tmp_path / "eurusd.csv"
    _write_csv(dataset)
    manifest = build_manifest(
        dataset,
        source_name="source",
        source_url="https://example.com/data",
        instrument="EURUSD",
        timeframe="1D",
        retrieved_at_utc="2026-08-19T12:00:00+00:00",
    )

    dataset.write_text(dataset.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="dataset_sha256_mismatch"):
        verify_manifest(manifest, dataset)
