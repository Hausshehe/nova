"""Download daily EURUSD OHLCV data into Nova's research format.

The first source (Stooq) started returning anti-bot HTML instead of CSV. This
helper now uses a public raw GitHub dataset with a stable CSV schema. It keeps
the ingestion dependency-free and performs no broker or trading actions.

The upstream dataset stores EURUSD prices scaled by 100000; this script
normalizes them back to ordinary FX prices.
"""

from __future__ import annotations

import argparse
import csv
import io
import urllib.request
from pathlib import Path


EURUSD_URL = "https://raw.githubusercontent.com/komo135/forex-historical-data/main/EURUSD/EURUSDd1.csv"


def download(symbol: str, output: Path) -> int:
    normalized_symbol = symbol.strip().lower()
    if normalized_symbol != "eurusd":
        raise ValueError("The current first experiment supports only symbol 'eurusd'.")

    request = urllib.request.Request(
        EURUSD_URL,
        headers={"User-Agent": "NovaResearch/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(text))
    required = {"Date", "open", "high", "low", "close", "tick_volume"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise RuntimeError(f"unexpected EURUSD response columns: {reader.fieldnames!r}")

    rows = []
    for row in reader:
        scale = 100000.0
        rows.append(
            {
                "timestamp": f"{row['Date']}T00:00:00Z",
                "open": float(row["open"]) / scale,
                "high": float(row["high"]) / scale,
                "low": float(row["low"]) / scale,
                "close": float(row["close"]) / scale,
                "volume": float(row["tick_volume"] or 0),
            }
        )

    if not rows:
        raise RuntimeError("no EURUSD rows returned")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"DATA_SOURCE: {EURUSD_URL}")
    print("SOURCE_SCHEMA: Date,open,high,low,close,tick_volume")
    print("PRICE_NORMALIZATION: divide OHLC by 100000")
    print(f"ROWS: {len(rows)}")
    print(f"FIRST_TIMESTAMP: {rows[0]['timestamp']}")
    print(f"LAST_TIMESTAMP: {rows[-1]['timestamp']}")
    print(f"OUTPUT: {output}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", help="currently supported: eurusd")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    download(args.symbol, args.output)


if __name__ == "__main__":
    main()
