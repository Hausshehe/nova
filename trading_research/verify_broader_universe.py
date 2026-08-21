"""Strict verifier for the frozen Experiment 2 26-dataset universe."""

from __future__ import annotations

from pathlib import Path

from .data import load_csv
from .dukascopy_history import INSTRUMENTS, TIMEFRAMES


def verify_universe(data_dir: str | Path) -> list[tuple[str, str]]:
    """Validate exactly the frozen 13 x 2 dataset universe and reject extras."""
    root = Path(data_dir)
    expected = {(instrument, timeframe) for instrument in INSTRUMENTS for timeframe in TIMEFRAMES}
    actual = {
        (path.name.rsplit("_", 1)[0], path.stem.rsplit("_", 1)[-1])
        for path in root.glob("*.csv")
        if path.name != "manifest.csv"
    }
    missing = expected - actual
    extras = actual - expected
    if missing:
        raise ValueError(f"universe_missing_datasets:{sorted(missing)}")
    if extras:
        raise ValueError(f"universe_extra_datasets:{sorted(extras)}")

    verified: list[tuple[str, str]] = []
    for instrument, timeframe in sorted(expected):
        path = root / f"{instrument}_{timeframe}.csv"
        bars = load_csv(path)
        if len(bars) < 100:
            raise ValueError(f"insufficient_bars:{instrument}:{timeframe}:{len(bars)}")

        # load_csv() returns the canonical research Bar type, while
        # dukascopy_history._deduplicate_and_validate() operates on its
        # separate acquisition Candle type. Do not mix those representations.
        # load_csv() has already validated OHLCV fields and chronological order;
        # this additional pass enforces strict timestamp uniqueness explicitly.
        timestamps = [bar.timestamp for bar in bars]
        if len(timestamps) != len(set(timestamps)):
            raise ValueError(f"duplicate_timestamps:{instrument}:{timeframe}")
        if timestamps != sorted(timestamps):
            raise ValueError(f"dataset_not_chronological:{instrument}:{timeframe}")

        verified.append((instrument, timeframe))
    return verified


if __name__ == "__main__":
    verified = verify_universe("data/research/universe_v2")
    print(f"FROZEN UNIVERSE VERIFIED datasets={len(verified)}")
