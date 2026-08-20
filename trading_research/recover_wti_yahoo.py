"""Recover the frozen Experiment 2 WTI 1D dataset from Yahoo Finance."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .dukascopy_history import write_csv
from .yahoo_history import YAHOO_WTI_SOURCE, fetch_wti_1d

START_UTC = "2010-01-01T00:00:00+00:00"
END_UTC = "2026-01-01T00:00:00+00:00"
TARGET = Path("data/research/universe_v2/WTI_1D.csv")


def recover_wti_1d(target: str | Path = TARGET) -> tuple[int, str]:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    candles = fetch_wti_1d(start_utc=START_UTC, end_utc=END_UTC)
    if len(candles) < 3000:
        raise ValueError(f"insufficient_bars:WTI:1D:{len(candles)}")
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        digest = write_csv(candles, temporary)
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(
        f"WTI YAHOO RECOVERY COMPLETE bars={len(candles)} sha256={digest} "
        f"source={YAHOO_WTI_SOURCE}",
        flush=True,
    )
    return len(candles), digest


if __name__ == "__main__":
    recover_wti_1d()
