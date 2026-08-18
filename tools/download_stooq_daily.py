"""Download a daily OHLCV CSV into Nova's research data format.

This is a thin, dependency-free ingestion helper. It does not place orders or
connect to a broker. The source URL and downloaded file are recorded so a
research run remains reproducible.
"""

from __future__ import annotations

import argparse
import csv
import io
import urllib.request
from pathlib import Path


STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"


def download(symbol: str, output: Path) -> int:
    url = STOOQ_URL.format(symbol=symbol.lower())
    request = urllib.request.Request(url, headers={"User-Agent": "NovaResearch/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()

    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise RuntimeError(
            f"unexpected Stooq response columns: {reader.fieldnames!r}"
        )

    rows = []
    for row in reader:
        rows.append(
            {
                "timestamp": f"{row['Date']}T00:00:00Z",
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
                "volume": row["Volume"] or "0",
            }
        )

    if not rows:
        raise RuntimeError(f"no rows returned for {symbol!r}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"DATA_SOURCE: {url}")
    print(f"ROWS: {len(rows)}")
    print(f"OUTPUT: {output}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", help="Stooq symbol, e.g. eurusd or spy.us")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    download(args.symbol, args.output)


if __name__ == "__main__":
    main()
