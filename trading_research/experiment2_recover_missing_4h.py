from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

from trading_research.dukascopy_history import DukascopyClient, write_csv

ROOT = Path("data/research/universe_v2")
SOURCE_REPO = "https://github.com/FutureSharks/financial-data.git"
SOURCE_COMMIT = "7ba1d404aa8b0e1c0f71321acebadcbfb9bcca8d"


def write_atomic(candles, target: Path) -> str:
    temp_path = None
    try:
        with NamedTemporaryFile(prefix=f".{target.name}.", suffix=".tmp", dir=ROOT, delete=False) as temp:
            temp_path = Path(temp.name)
        digest = write_csv(candles, temp_path)
        os.replace(temp_path, target)
        temp_path = None
        return digest
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def recover_dukascopy(instrument: str, start: str) -> None:
    target = ROOT / f"{instrument}_4H.csv"
    print(f"RECOVER {instrument} 4H", flush=True)
    candles = DukascopyClient().historical_prices(
        instrument=instrument,
        timeframe="4H",
        start_utc=start,
        end_utc="2026-01-01T00:00:00+00:00",
        progress=lambda message: print(message, flush=True),
    )
    if len(candles) < 100:
        raise SystemExit(f"insufficient_bars:{instrument}:4H:{len(candles)}")
    years = {int(c.timestamp_utc[:4]) for c in candles}
    required = set(range(2011, 2026)) if instrument == "NAS100" else set(range(2010, 2026))
    if not required.issubset(years):
        raise SystemExit(f"coverage_failure:{instrument}:4H:{sorted(required-years)}")
    digest = write_atomic(candles, target)
    print(f"RECOVERY COMPLETE {instrument} 4H bars={len(candles)} sha256={digest}", flush=True)


def build_us500_early() -> None:
    work = Path("/tmp/financial-data")
    if work.exists():
        subprocess.run(["rm", "-rf", str(work)], check=True)
    subprocess.run(["git", "clone", "--depth=1", "--filter=blob:none", "--sparse", SOURCE_REPO, str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "fetch", "--no-tags", "origin", SOURCE_COMMIT], check=True)
    subprocess.run(["git", "-C", str(work), "checkout", SOURCE_COMMIT], check=True)
    subprocess.run([
        "git", "-C", str(work), "sparse-checkout", "set",
        "pyfinancialdata/data/currencies/oanda/SPX500_USD/2010",
    ], check=True)

    source_root = work / "pyfinancialdata/data/currencies/oanda/SPX500_USD/2010"
    files = sorted(source_root.glob("*.csv"))
    if len(files) != 12:
        raise SystemExit(f"oanda_spx500_2010_month_file_count:{len(files)}")

    frames = []
    for path in files:
        frame = pd.read_csv(path, parse_dates=["time"])
        required = {"time", "close", "high", "low", "open", "volume"}
        if set(frame.columns) != required:
            raise SystemExit(f"oanda_spx500_schema:{path}:{sorted(frame.columns)}")
        frames.append(frame)

    minute = pd.concat(frames, ignore_index=True)
    minute["time"] = pd.to_datetime(minute["time"], utc=True)
    minute = minute[(minute["time"] >= "2010-01-01") & (minute["time"] < "2011-01-01")]
    minute = minute.drop_duplicates(subset=["time"], keep="first").sort_values("time")
    if minute.empty:
        raise SystemExit("oanda_spx500_2010_empty")

    for row in minute.itertuples(index=False):
        if not (row.low <= row.open <= row.high and row.low <= row.close <= row.high):
            raise SystemExit(f"oanda_spx500_invalid_ohlc:{row.time}")

    minute = minute.set_index("time")
    grouped = minute.resample("4h", origin="epoch", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        observations=("close", "size"),
    )
    grouped = grouped[grouped["observations"] > 0].drop(columns=["observations"]).sort_index()
    grouped = grouped[(grouped.index >= "2010-01-01") & (grouped.index < "2011-01-01")]
    out = grouped.reset_index()
    out.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    target = ROOT / "US500_4H.csv"
    temp_path = None
    try:
        with NamedTemporaryFile(prefix=f".{target.name}.", suffix=".tmp", dir=ROOT, delete=False) as temp:
            temp_path = Path(temp.name)
        out.to_csv(temp_path, index=False)
        digest = hashlib.sha256(temp_path.read_bytes()).hexdigest()
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    meta = {
        "instrument": "US500",
        "timeframe": "4H",
        "early_source": "FutureSharks/financial-data OANDA SPX500_USD minute archive",
        "early_source_commit": SOURCE_COMMIT,
        "early_period": "[2010-01-01, 2011-01-01)",
        "later_source": "Dukascopy native 4H",
        "later_period": "[2011-01-01, 2026-01-01)",
        "aggregation": "UTC 4H from minute OHLCV for early period",
        "rows_early": int(len(out)),
        "sha256_early": digest,
    }
    (ROOT / "US500_4H.provenance.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"OANDA US500 EARLY COMPLETE bars={len(out)} first={out.timestamp.iloc[0]} last={out.timestamp.iloc[-1]}", flush=True)


def splice_us500_late() -> None:
    early = pd.read_csv(ROOT / "US500_4H.csv")
    early["timestamp"] = pd.to_datetime(early["timestamp"], utc=True)
    candles = DukascopyClient().historical_prices(
        instrument="US500",
        timeframe="4H",
        start_utc="2011-01-01T00:00:00+00:00",
        end_utc="2026-01-01T00:00:00+00:00",
        progress=lambda message: print(message, flush=True),
    )
    required_years = set(range(2011, 2026))
    years = {int(c.timestamp_utc[:4]) for c in candles}
    if not required_years.issubset(years):
        raise SystemExit(f"coverage_failure:US500:4H:{sorted(required_years-years)}")
    late = pd.DataFrame([{
        "timestamp": c.timestamp_utc,
        "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume,
    } for c in candles])
    late["timestamp"] = pd.to_datetime(late["timestamp"], utc=True)
    combined = pd.concat([early, late], ignore_index=True)
    combined = combined[(combined["timestamp"] >= "2010-01-01") & (combined["timestamp"] < "2026-01-01")]
    combined = combined.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="first")
    for row in combined.itertuples(index=False):
        if not (row.low <= row.open <= row.high and row.low <= row.close <= row.high):
            raise SystemExit(f"us500_splice_invalid_ohlc:{row.timestamp}")
    target = ROOT / "US500_4H.csv"
    temp_path = None
    try:
        with NamedTemporaryFile(prefix=f".{target.name}.", suffix=".tmp", dir=ROOT, delete=False) as temp:
            temp_path = Path(temp.name)
        combined.assign(timestamp=combined["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")).to_csv(temp_path, index=False, columns=["timestamp","open","high","low","close","volume"])
        digest = hashlib.sha256(temp_path.read_bytes()).hexdigest()
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    meta = json.loads((ROOT / "US500_4H.provenance.json").read_text(encoding="utf-8"))
    meta.update({"rows_total": int(len(combined)), "sha256_total": digest})
    (ROOT / "US500_4H.provenance.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"RECOVERY COMPLETE US500 4H bars={len(combined)} sha256={digest}", flush=True)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    recover_dukascopy("NAS100", "2011-09-01T00:00:00+00:00")
    recover_dukascopy("NZDUSD", "2010-01-01T00:00:00+00:00")
    build_us500_early()
    splice_us500_late()


if __name__ == "__main__":
    main()
