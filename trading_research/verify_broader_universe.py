"""Verify the frozen broader-universe manifest before any research evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .dukascopy_history import INSTRUMENTS, TIMEFRAMES
from .data import load_csv

DATA_DIR = Path("data/research/universe_v2")
MANIFEST_PATH = DATA_DIR / "manifest.json"


def verify_manifest(data_dir: Path = DATA_DIR) -> dict:
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("manifest_missing")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("manifest_not_a_list")

    expected = {(instrument, timeframe) for instrument in INSTRUMENTS for timeframe in TIMEFRAMES}
    seen: set[tuple[str, str]] = set()
    checked = []

    for item in payload:
        instrument = item.get("instrument")
        timeframe = item.get("timeframe")
        key = (instrument, timeframe)
        if key in seen:
            raise ValueError(f"duplicate_manifest_entry:{instrument}:{timeframe}")
        if key not in expected:
            raise ValueError(f"unexpected_manifest_entry:{instrument}:{timeframe}")
        seen.add(key)

        filename = f"{instrument}_{timeframe}.csv"
        path = data_dir / filename
        if not path.exists():
            raise ValueError(f"dataset_missing:{filename}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item.get("sha256"):
            raise ValueError(f"hash_mismatch:{filename}:{digest}:{item.get('sha256')}")
        bars = load_csv(path)
        if len(bars) != int(item.get("bars", -1)):
            raise ValueError(f"bar_count_mismatch:{filename}:{len(bars)}:{item.get('bars')}")
        if bars[0].timestamp.isoformat() != item.get("start_utc"):
            raise ValueError(f"start_timestamp_mismatch:{filename}")
        if bars[-1].timestamp.isoformat() != item.get("end_utc"):
            raise ValueError(f"end_timestamp_mismatch:{filename}")
        checked.append({"instrument": instrument, "timeframe": timeframe, "bars": len(bars), "sha256": digest})

    if seen != expected or len(payload) != len(expected):
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ValueError(f"manifest_coverage_mismatch:missing={missing}:extra={extra}")

    return {"datasets": len(checked), "checked": checked}


if __name__ == "__main__":
    result = verify_manifest()
    print(f"verified_datasets={result['datasets']}")
    print("MANIFEST_VERIFICATION=PASS")
