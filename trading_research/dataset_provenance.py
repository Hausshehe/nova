"""Provenance and integrity checks for independent research datasets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from .data import load_csv


@dataclass(frozen=True)
class DatasetManifest:
    source_name: str
    source_url: str
    instrument: str
    timeframe: str
    path: str
    sha256: str
    rows: int
    start_timestamp: str
    end_timestamp: str
    retrieved_at_utc: str

    def validate(self) -> None:
        if not self.source_name.strip():
            raise ValueError("source_name is required")
        if not self.source_url.strip():
            raise ValueError("source_url is required")
        if not self.instrument.strip():
            raise ValueError("instrument is required")
        if not self.timeframe.strip():
            raise ValueError("timeframe is required")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character hex digest")
        int(self.sha256, 16)
        if self.rows < 2:
            raise ValueError("rows must be at least 2")
        datetime.fromisoformat(self.start_timestamp)
        datetime.fromisoformat(self.end_timestamp)
        datetime.fromisoformat(self.retrieved_at_utc)
        if self.end_timestamp <= self.start_timestamp:
            raise ValueError("end_timestamp must be after start_timestamp")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    path: str | Path,
    *,
    source_name: str,
    source_url: str,
    instrument: str,
    timeframe: str,
    retrieved_at_utc: str | None = None,
) -> DatasetManifest:
    csv_path = Path(path)
    bars = load_csv(str(csv_path))
    manifest = DatasetManifest(
        source_name=source_name,
        source_url=source_url,
        instrument=instrument,
        timeframe=timeframe,
        path=str(csv_path),
        sha256=sha256_file(csv_path),
        rows=len(bars),
        start_timestamp=bars[0].timestamp.isoformat(),
        end_timestamp=bars[-1].timestamp.isoformat(),
        retrieved_at_utc=retrieved_at_utc or datetime.now(timezone.utc).isoformat(),
    )
    manifest.validate()
    return manifest


def write_manifest(manifest: DatasetManifest, path: str | Path) -> None:
    manifest.validate()
    Path(path).write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_manifest(manifest: DatasetManifest, path: str | Path) -> None:
    """Verify bytes and chronological metadata against a frozen manifest."""
    manifest.validate()
    candidate = Path(path)
    bars = load_csv(str(candidate))
    actual_hash = sha256_file(candidate)
    if actual_hash != manifest.sha256:
        raise ValueError("dataset_sha256_mismatch")
    if len(bars) != manifest.rows:
        raise ValueError("dataset_row_count_mismatch")
    if bars[0].timestamp.isoformat() != manifest.start_timestamp:
        raise ValueError("dataset_start_timestamp_mismatch")
    if bars[-1].timestamp.isoformat() != manifest.end_timestamp:
        raise ValueError("dataset_end_timestamp_mismatch")
