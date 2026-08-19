"""One-time migration of broader-campaign artifacts produced by the legacy decoder.

The legacy Dukascopy decoder used the native candle field order incorrectly:
open, close, low, high instead of open, high, low, close. This helper is deliberately
restricted to the known legacy source run and repairs only daily CSVs by swapping
high/close. Four-hour CSVs are not repaired because their aggregate high/close values
were computed from the wrong fields; callers must rebuild them from raw H1 data.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

LEGACY_SOURCE_RUN_ID = "32293018258"


def _atomic_write(path: Path, rows: list[dict[str, str]]) -> None:
    with NamedTemporaryFile("w", newline="", encoding="utf-8", dir=path.parent, delete=False) as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)
        temp_name = handle.name
    os.replace(temp_name, path)


def repair_legacy_daily_artifact(path: str | Path) -> None:
    target = Path(path)
    with target.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["timestamp", "open", "high", "low", "close", "volume"]:
            raise ValueError(f"unexpected_csv_schema:{target}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"empty_dataset:{target}")
    for row in rows:
        row["high"], row["close"] = row["close"], row["high"]
        low = float(row["low"])
        open_ = float(row["open"])
        high = float(row["high"])
        close = float(row["close"])
        if not (low <= open_ <= high and low <= close <= high):
            raise ValueError(f"legacy_repair_invalid_ohlc:{target}:{row['timestamp']}")
    _atomic_write(target, rows)


def migrate_legacy_artifacts(root: str | Path, *, source_run_id: str) -> tuple[list[str], list[str]]:
    if source_run_id != LEGACY_SOURCE_RUN_ID:
        raise ValueError(f"legacy_migration_source_run_mismatch:{source_run_id}")
    root_path = Path(root)
    repaired_daily: list[str] = []
    removed_four_hour: list[str] = []
    for path in sorted(root_path.glob("*_1D.csv")):
        repair_legacy_daily_artifact(path)
        repaired_daily.append(path.name)
    for path in sorted(root_path.glob("*_4H.csv")):
        path.unlink()
        removed_four_hour.append(path.name)
    return repaired_daily, removed_four_hour
