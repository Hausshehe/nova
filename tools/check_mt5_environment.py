"""Gate-0 check for the Windows MetaTrader 5 research environment.

This script is intentionally read-only: it never places, modifies, or closes
orders. It verifies the Python package, connects to an already-running MT5
terminal, retrieves a small historical OHLCV sample, and validates it using
Nova's deterministic research data contract.

Exit codes:
    0  Gate passed.
    2  Environment/package/terminal connection failure.
    3  Market-data retrieval failure.
    4  Retrieved data failed Nova's data contract.
"""

from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trading_research.data import validate_ohlcv_rows


DEFAULT_SYMBOL = "EURUSD"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_BARS = 200


def _timeframe_value(mt5: Any, name: str) -> int:
    value = getattr(mt5, f"TIMEFRAME_{name.upper()}", None)
    if value is None:
        raise ValueError(f"Unsupported MT5 timeframe: {name}")
    return value


def _normalize_rows(rates: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in rates:
        timestamp = int(row["time"])
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        rows.append(
            {
                "timestamp": dt.isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["tick_volume"]),
            }
        )
    return rows


def run_check(symbol: str, timeframe: str, bars: int) -> int:
    if importlib.util.find_spec("MetaTrader5") is None:
        print("FAIL: MetaTrader5 Python package is not installed.")
        return 2

    import MetaTrader5 as mt5  # type: ignore

    print("GATE_0: MT5 research environment")
    print(f"python: {__import__('sys').version.split()[0]}")
    print(f"package: MetaTrader5 {getattr(mt5, '__version__', 'unknown')}")
    print(f"symbol: {symbol}")
    print(f"timeframe: {timeframe}")
    print(f"bars_requested: {bars}")

    if not mt5.initialize():
        print(f"FAIL: MT5 initialize() failed: {mt5.last_error()}")
        return 2

    try:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        if terminal is None:
            print(f"FAIL: MT5 terminal_info() unavailable: {mt5.last_error()}")
            return 2

        print(f"terminal_connected: {bool(getattr(terminal, 'connected', False))}")
        print(f"terminal_path: {getattr(terminal, 'path', '')}")
        if account is not None:
            print(f"account_login: {getattr(account, 'login', '')}")
            print(f"account_server: {getattr(account, 'server', '')}")
            print("account_data_read: PASS")
        else:
            print(f"account_data_read: unavailable ({mt5.last_error()})")

        if not mt5.symbol_select(symbol, True):
            print(f"FAIL: symbol_select({symbol!r}) failed: {mt5.last_error()}")
            return 3

        timeframe_value = _timeframe_value(mt5, timeframe)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=30)
        rates = mt5.copy_rates_range(symbol, timeframe_value, start, end)
        if rates is None or len(rates) == 0:
            print(f"FAIL: copy_rates_range returned no data: {mt5.last_error()}")
            return 3

        selected = rates[-bars:]
        rows = _normalize_rows(selected)
        print(f"bars_received: {len(rows)}")
        print(f"first_timestamp: {rows[0]['timestamp']}")
        print(f"last_timestamp: {rows[-1]['timestamp']}")

        report = validate_ohlcv_rows(rows)
        print(f"data_contract: {'PASS' if report.ok else 'FAIL'}")
        if not report.ok:
            for reason in report.reasons:
                print(f"data_contract_reason: {reason}")
            return 4

        print("GATE_0_RESULT: PASS")
        print("No trading actions were requested or performed.")
        return 0
    finally:
        mt5.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--bars", type=int, default=DEFAULT_BARS)
    args = parser.parse_args()
    if args.bars <= 0:
        parser.error("--bars must be positive")
    return run_check(args.symbol, args.timeframe, args.bars)


if __name__ == "__main__":
    raise SystemExit(main())
