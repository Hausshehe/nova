"""One-time invalidation of the WTI 4H artifact from the legacy source run."""

from __future__ import annotations

from pathlib import Path

LEGACY_SOURCE_RUN_ID = "32293018258"
LEGACY_WTI_4H_DATASET = "WTI_4H.csv"


def invalidate_legacy_wti_4h(root: str | Path, *, source_run_id: str) -> str:
    """Remove the old WTI 4H artifact so it is rebuilt using corrected feed routing."""
    if source_run_id != LEGACY_SOURCE_RUN_ID:
        raise ValueError(f"legacy_migration_source_run_mismatch:{source_run_id}")
    target = Path(root) / LEGACY_WTI_4H_DATASET
    if not target.is_file():
        raise ValueError(f"legacy_wti_4h_missing:{target}")
    target.unlink()
    return LEGACY_WTI_4H_DATASET
