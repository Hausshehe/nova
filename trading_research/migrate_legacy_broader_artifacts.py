"""One-time migration of broader-campaign artifacts produced by the legacy decoder.

The legacy Dukascopy decoder used the native candle field order incorrectly:
open, close, low, high instead of open, high, low, close. This helper is deliberately
restricted to the known legacy source run. It repairs only the known daily artifacts
by swapping high/close and removes only the known stale four-hour artifacts, which must
then be rebuilt from corrected raw hourly data.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

LEGACY_SOURCE_RUN_ID = "32293018258"

# Exact successful artifact snapshot from the known cancelled source run.
LEGACY_DAILY_DATASETS = (
    "AUDUSD_1D.csv",
    "EURUSD_1D.csv",
    "GBPUSD_1D.csv",
    "NAS100_1D.csv",
    "NZDUSD_1D.csv",
    "US30_1D.csv",
    "US500_1D.csv",
    "USDCAD_1D.csv",
    "USDCHF_1D.csv",
    "USDJPY_1D.csv",
    "XAGUSD_1D.csv",
    "XAUUSD_1D.csv",
)

LEGACY_FOUR_HOUR_DATASETS = (
    "AUDUSD_4H.csv",
    "GBPUSD_4H.csv",
    "US30_4H.csv",
    "USDCAD_4H.csv",
    "USDCHF_4H.csv",
    "USDJPY_4H.csv",
    "WTI_4H.csv",
    "XAGUSD_4H.csv",
    "XAUUSD_4H.csv",
)


def _atomic_write(path: Path, rows: list[dict[str, str]]) -> None:
    with NamedTemporaryFile(
        "w", newline="", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
        )
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
    actual_csv_names = {path.name for path in root_path.glob("*.csv")}
    expected_names = set(LEGACY_DAILY_DATASETS) | set(LEGACY_FOUR_HOUR_DATASETS)
    unexpected = sorted(actual_csv_names - expected_names)
    if unexpected:
        raise ValueError(f"legacy_migration_unexpected_files:{','.join(unexpected)}")

    missing_daily = [name for name in LEGACY_DAILY_DATASETS if not (root_path / name).is_file()]
    missing_four_hour = [name for name in LEGACY_FOUR_HOUR_DATASETS if not (root_path / name).is_file()]
    if missing_daily:
        raise ValueError(f"legacy_migration_missing_daily:{','.join(missing_daily)}")
    if missing_four_hour:
        raise ValueError(f"legacy_migration_missing_four_hour:{','.join(missing_four_hour)}")

    repaired_daily: list[str] = []
    for name in LEGACY_DAILY_DATASETS:
        repair_legacy_daily_artifact(root_path / name)
        repaired_daily.append(name)

    removed_four_hour: list[str] = []
    for name in LEGACY_FOUR_HOUR_DATASETS:
        path = root_path / name
        path.unlink()
        removed_four_hour.append(name)

    return repaired_daily, removed_four_hour
