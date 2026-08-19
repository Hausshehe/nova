"""Immutable evidence identity helpers for research provenance.

This module centralizes evidence identity so future gates can compare the
recorded dataset fingerprint without depending on the historical file still
being present on disk.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping, Any


def sha256_file(path: str | Path) -> str | None:
    candidate = Path(path)
    if not candidate.is_file():
        return None
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recorded_dataset_sha256(record: Mapping[str, Any]) -> str | None:
    """Return immutable dataset identity carried by a stored experiment."""
    value = record.get("dataset_sha256")
    return str(value) if isinstance(value, str) and value else None


def same_evidence(record: Mapping[str, Any], current_dataset_sha256: str | None) -> bool:
    """Compare current evidence against recorded provenance, never old paths."""
    recorded = recorded_dataset_sha256(record)
    return recorded is not None and current_dataset_sha256 is not None and recorded == current_dataset_sha256
