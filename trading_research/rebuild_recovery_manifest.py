"""Build a deterministic frozen-universe manifest from recovered CSV datasets."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .data import load_csv
from .dukascopy_history import DatasetManifest, INSTRUMENTS, TIMEFRAMES, save_manifest
from .yahoo_history import YAHOO_WTI_SOURCE


DATASET_SOURCES = {
    ("WTI", "1D"): YAHOO_WTI_SOURCE,
}


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
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifests.append(
            DatasetManifest(
                instrument=instrument,
                timeframe=timeframe,
                start_utc=bars[0].timestamp.isoformat(),
                end_utc=bars[-1].timestamp.isoformat(),
                sha256=digest,
                bars=len(bars),
                source=DATASET_SOURCES.get(
                    (instrument, timeframe),
                    "recovered_from_frozen_source_artifacts_and_dukascopy",
                ),
            )
        )

    save_manifest(manifests, root / "manifest.json")
    return manifests


if __name__ == "__main__":
    result = rebuild_manifest("data/research/universe_v2")
    print(f"RECOVERY MANIFEST BUILT datasets={len(result)}")
