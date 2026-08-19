from pathlib import Path

import pytest

from trading_research.verify_broader_universe import verify_broader_universe


def _write_dataset(root: Path, name: str, *, valid: bool = True) -> None:
    root.joinpath(name).write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-01T00:00:00+00:00,100,110,90,105,1\n"
        + ("2024-01-01T01:00:00+00:00,105,115,100,110,2\n" if valid else "2024-01-01T01:00:00+00:00,120,110,90,100,2\n")
        * 50,
        encoding="utf-8",
    )


def test_verify_broader_universe_requires_every_frozen_dataset(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing_frozen_dataset"):
        verify_broader_universe(tmp_path)


def test_verify_broader_universe_rejects_bad_ohlc(tmp_path: Path) -> None:
    from trading_research.dukascopy_history import INSTRUMENTS, TIMEFRAMES

    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            _write_dataset(tmp_path, f"{instrument}_{timeframe}.csv")
    _write_dataset(tmp_path, "EURUSD_1D.csv", valid=False)

    with pytest.raises(ValueError, match="ohlc_integrity_failure:EURUSD:1D"):
        verify_broader_universe(tmp_path)
