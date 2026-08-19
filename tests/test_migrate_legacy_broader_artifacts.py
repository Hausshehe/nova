from pathlib import Path

import pytest

from trading_research.migrate_legacy_broader_artifacts import (
    LEGACY_DAILY_DATASETS,
    LEGACY_FOUR_HOUR_DATASETS,
    LEGACY_SOURCE_RUN_ID,
    migrate_legacy_artifacts,
    repair_legacy_daily_artifact,
)


def _write_legacy_csv(path: Path, *, high: int = 110, close: int = 105) -> None:
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        f"2024-01-01T00:00:00+00:00,100,{high},90,{close},1\n",
        encoding="utf-8",
    )


def test_legacy_snapshot_counts_and_missing_contexts_are_exact() -> None:
    assert len(LEGACY_DAILY_DATASETS) == 12
    assert len(LEGACY_FOUR_HOUR_DATASETS) == 10
    expected_missing = {
        "NAS100_4H.csv",
        "NZDUSD_4H.csv",
        "US500_4H.csv",
        "WTI_1D.csv",
    }
    assert expected_missing.isdisjoint(set(LEGACY_DAILY_DATASETS) | set(LEGACY_FOUR_HOUR_DATASETS))
    assert len(LEGACY_DAILY_DATASETS) + len(LEGACY_FOUR_HOUR_DATASETS) + len(expected_missing) == 26
    assert LEGACY_SOURCE_RUN_ID == "32293018258"


def test_repair_legacy_daily_artifact_swaps_only_high_and_close(tmp_path: Path) -> None:
    dataset = tmp_path / "EURUSD_1D.csv"
    _write_legacy_csv(dataset, high=105, close=110)
    repair_legacy_daily_artifact(dataset)
    assert dataset.read_text(encoding="utf-8").splitlines()[1].endswith(",110,90,105,1")


def test_repair_legacy_daily_artifact_rejects_bad_result(tmp_path: Path) -> None:
    dataset = tmp_path / "EURUSD_1D.csv"
    _write_legacy_csv(dataset, high=80, close=110)
    with pytest.raises(ValueError, match="legacy_repair_invalid_ohlc"):
        repair_legacy_daily_artifact(dataset)


def _write_complete_legacy_snapshot(root: Path) -> None:
    for name in LEGACY_DAILY_DATASETS:
        _write_legacy_csv(root / name, high=105, close=110)
    for name in LEGACY_FOUR_HOUR_DATASETS:
        (root / name).write_text("stale\n", encoding="utf-8")


def test_migration_requires_exact_known_legacy_snapshot(tmp_path: Path) -> None:
    _write_complete_legacy_snapshot(tmp_path)
    repaired, removed = migrate_legacy_artifacts(tmp_path, source_run_id=LEGACY_SOURCE_RUN_ID)
    assert repaired == list(LEGACY_DAILY_DATASETS)
    assert removed == list(LEGACY_FOUR_HOUR_DATASETS)
    assert not any((tmp_path / name).exists() for name in LEGACY_FOUR_HOUR_DATASETS)


def test_migration_rejects_unexpected_file(tmp_path: Path) -> None:
    _write_complete_legacy_snapshot(tmp_path)
    (tmp_path / "unexpected_1D.csv").write_text("stale\n", encoding="utf-8")
    with pytest.raises(ValueError, match="legacy_migration_unexpected_files"):
        migrate_legacy_artifacts(tmp_path, source_run_id=LEGACY_SOURCE_RUN_ID)


def test_migration_rejects_incomplete_snapshot(tmp_path: Path) -> None:
    _write_legacy_csv(tmp_path / LEGACY_DAILY_DATASETS[0], high=105, close=110)
    with pytest.raises(ValueError, match="legacy_migration_missing_daily"):
        migrate_legacy_artifacts(tmp_path, source_run_id=LEGACY_SOURCE_RUN_ID)


def test_migration_rejects_unknown_source_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="legacy_migration_source_run_mismatch"):
        migrate_legacy_artifacts(tmp_path, source_run_id="different-run")
