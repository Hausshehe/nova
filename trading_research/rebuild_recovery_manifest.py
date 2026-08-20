"""Build a deterministic frozen-universe manifest from recovered CSV datasets."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .data import load_csv
from .dukascopy_history import (
    DatasetManifest,
    INSTRUMENTS,
    TIMEFRAMES,
    _deduplicate_and_validate,
)


def rebuild_manifest(data_dir: str | Path) -> list[DatasetManifest]:
    root = Path(data_dir)
    expected = [(instrument, timeframe) for instrument in INSTRUMENTS for timeframe in TIMEFRAMES]
    manifests: list[DatasetManifest] = []

    for instrument, timeframe in expected:
        path = root / f"{instrument}_{timeframe}.csv"
        if not path.is_file():
            raise ValueError(f"dataset_missing:{path.name}")
        bars = load_csv(path)
        if len(bars) < 100:
            raise ValueError(f"insufficient_bars:{instrument}:{timeframe}:{len(bars)}")

        # Certify only data that already satisfies the acquisition validator.
        validated = _deduplicate_and_validate(bars)
        if len(validated) != len(bars):
            raise ValueError(f"dataset_normalization_changed_rows:{instrument}:{timeframe}")
        if validated != bars:
            raise ValueError(f"dataset_not_in_canonical_order:{instrument}:{timeframe}")

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifests.append(
            DatasetManifest(
                instrument=instrument,
                timeframe=timeframe,
                start_utc=bars[0].timestamp.isoformat(),
                end_utc=bars[-1].timestamp.isoformat(),
                sha256=digest,
                bars=len(bars),
                source="recovered_from_frozen_source_artifacts_and_dukascopy",
            )
        )

    payload = [manifest.__dict__ for manifest in manifests]
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    fd, temp_name = tempfile.mkstemp(prefix=".manifest.", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, manifest_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    return manifests


if __name__ == "__main__":
    result = rebuild_manifest("data/research/universe_v2")
    print(f"RECOVERY MANIFEST BUILT datasets={len(result)}")
