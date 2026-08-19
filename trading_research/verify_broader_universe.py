"""Verify the frozen broader research universe before matrix execution."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .dukascopy_history import DATAFEED_BASE_URL, INSTRUMENTS, TIMEFRAMES

DEFAULT_ROOT = Path("data/research/universe_v2")
EXPECTED_DATASETS = len(INSTRUMENTS) * len(TIMEFRAMES)


def verify_broader_universe(root: str | Path = DEFAULT_ROOT) -> list[dict[str, object]]:
    root = Path(root)
    manifests: list[dict[str, object]] = []
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            path = root / f"{instrument}_{timeframe}.csv"
            if not path.is_file():
                raise ValueError(f"missing_frozen_dataset:{instrument}:{timeframe}")
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            if len(rows) < 100:
                raise ValueError(f"insufficient_frozen_dataset:{instrument}:{timeframe}:{len(rows)}")
            timestamps = [row["timestamp"] for row in rows]
            if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
                raise ValueError(f"timestamp_integrity_failure:{instrument}:{timeframe}")
            for row in rows:
                low = float(row["low"])
                open_ = float(row["open"])
                high = float(row["high"])
                close = float(row["close"])
                if not (low <= open_ <= high and low <= close <= high):
                    raise ValueError(
                        f"ohlc_integrity_failure:{instrument}:{timeframe}:{row['timestamp']}"
                    )
            manifests.append({
                "instrument": instrument,
                "timeframe": timeframe,
                "start_utc": timestamps[0],
                "end_utc": timestamps[-1],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bars": len(rows),
                "source": DATAFEED_BASE_URL,
                "price_units": "native_feed_units",
            })

    if len(manifests) != EXPECTED_DATASETS:
        raise ValueError(f"manifest_context_count:{len(manifests)}")
    root.joinpath("manifest.json").write_text(
        json.dumps(manifests, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifests


def main() -> None:
    manifests = verify_broader_universe()
    print(f"FROZEN UNIVERSE VERIFIED: datasets={len(manifests)}")


if __name__ == "__main__":
    main()
