from pathlib import Path

import pytest

from trading_research.migrate_legacy_broader_artifacts import (
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


def test_migration_is_restricted_to_known_source_run(tmp_path: Path) -> None:
    _write_legacy_csv(tmp_path / "EURUSD_1D.csv", high=105, close=110)
    (tmp_path / "EURUSD_4H.csv").write_text("stale\n", encoding="utf-8")
    repaired, removed = migrate_legacy_artifacts(tmp_path, source_run_id=LEGACY_SOURCE_RUN_ID)
    assert repaired == ["EURUSD_1D.csv"]
    assert removed == ["EURUSD_4H.csv"]
    assert not (tmp_path / "EURUSD_4H.csv").exists()


def test_migration_rejects_unknown_source_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="legacy_migration_source_run_mismatch"):
        migrate_legacy_artifacts(tmp_path, source_run_id="different-run")
