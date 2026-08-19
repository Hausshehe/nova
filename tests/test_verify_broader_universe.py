from pathlib import Path

import pytest

from trading_research.verify_broader_universe import verify_broader_universe


def _write_dataset(root: Path, name: str, *, valid: bool = True) -> None:
    lines = ["timestamp,open,high,low,close,volume"]
    for index in range(100):
        hour = index
        if valid:
            lines.append(
                f"2024-01-01T{hour:02d}:00:00+00:00,100,110,90,105,1"
            )
        else:
            lines.append(
                f"2024-01-01T{hour:02d}:00:00+00:00,120,110,90,100,1"
            )
    root.joinpath(name).write_text("\n".join(lines) + "\n", encoding="utf-8")


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
