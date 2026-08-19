from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from trading_research.verify_broader_universe import verify_manifest


def _write_dataset(root: Path, instrument: str, timeframe: str) -> str:
    path = root / f"{instrument}_{timeframe}.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2020-01-01T00:00:00+00:00,1,2,0.5,1.5,1\n"
        "2020-01-02T00:00:00+00:00,1.5,2.5,1,2,1\n",
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_verification_rejects_missing_dataset(tmp_path: Path) -> None:
    manifest = []
    for instrument in ("EURUSD", "GBPUSD"):
        digest = _write_dataset(tmp_path, instrument, "1D")
        manifest.append({
            "instrument": instrument,
            "timeframe": "1D",
            "start_utc": "2020-01-01T00:00:00+00:00",
            "end_utc": "2020-01-02T00:00:00+00:00",
            "sha256": digest,
            "bars": 2,
        })
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest_coverage_mismatch"):
        verify_manifest(tmp_path)


def test_manifest_verification_rejects_hash_mismatch(tmp_path: Path) -> None:
    digest = _write_dataset(tmp_path, "EURUSD", "1D")
    manifest = [{
        "instrument": "EURUSD",
        "timeframe": "1D",
        "start_utc": "2020-01-01T00:00:00+00:00",
        "end_utc": "2020-01-02T00:00:00+00:00",
        "sha256": "0" * 64,
        "bars": 2,
    }]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert digest != manifest[0]["sha256"]
    with pytest.raises(ValueError, match="hash_mismatch"):
        verify_manifest(tmp_path)
