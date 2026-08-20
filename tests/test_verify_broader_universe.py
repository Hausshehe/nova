from pathlib import Path

from trading_research.dukascopy_history import INSTRUMENTS, TIMEFRAMES
from trading_research.verify_broader_universe import verify_universe


def _write_csv(path: Path) -> None:
    rows = ["timestamp,open,high,low,close,volume"]
    for day in range(1, 101):
        rows.append(f"2010-01-{day:02d}T00:00:00+00:00,1,2,0,1,1")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_verify_requires_exact_frozen_universe(tmp_path: Path):
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            _write_csv(tmp_path / f"{instrument}_{timeframe}.csv")

    verified = verify_universe(tmp_path)
    assert len(verified) == 26


def test_verify_rejects_missing_dataset(tmp_path: Path):
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            _write_csv(tmp_path / f"{instrument}_{timeframe}.csv")
    (tmp_path / "WTI_1D.csv").unlink()

    try:
        verify_universe(tmp_path)
    except ValueError as exc:
        assert "universe_missing_datasets" in str(exc)
    else:
        raise AssertionError("missing dataset was not rejected")
