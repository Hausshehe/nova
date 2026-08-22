"""Run the existing causal mean-reversion family on XAGUSD 4H development data.

This is a mechanism change after the Research Brain v1 regime-continuation
family produced no positive development effect. It uses only the development
period, fixed causal parameters, and realistic costs. It never loads or
references confirmation data.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from trading_research.backtest import run_long_flat
from trading_research.data import load_csv
from trading_research.dukascopy_history import DukascopyClient, write_csv
from trading_research.broader_campaign_runner import mean_reversion_signal_series

DEVELOPMENT_START_UTC = "2010-01-01T00:00:00+00:00"
DEVELOPMENT_END_UTC = "2023-01-01T00:00:00+00:00"
SYMBOL = "XAGUSD"
TIMEFRAME = "4H"
FEE_BPS_PER_SIDE = 1.0
SLIPPAGE_BPS_PER_SIDE = 1.0


def run(output_dir: str | Path) -> dict[str, object]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    candles = DukascopyClient().historical_prices(
        instrument=SYMBOL,
        timeframe=TIMEFRAME,
        start_utc=DEVELOPMENT_START_UTC,
        end_utc=DEVELOPMENT_END_UTC,
        progress=print,
    )
    if len(candles) < 250:
        raise ValueError(f"insufficient development bars: {len(candles)}")

    development_end = datetime.fromisoformat(DEVELOPMENT_END_UTC)
    last_candle = datetime.fromisoformat(candles[-1].timestamp_utc)
    if last_candle >= development_end:
        raise ValueError("development dataset crosses confirmation cutoff")

    dataset_path = output / f"{SYMBOL}_{TIMEFRAME}_development.csv"
    dataset_sha256 = write_csv(candles, dataset_path)
    bars = load_csv(dataset_path)

    states = mean_reversion_signal_series(bars)
    signal = lambda _bars, index: states[index]
    result = run_long_flat(
        bars,
        signal,
        fee_bps=FEE_BPS_PER_SIDE,
        slippage_bps=SLIPPAGE_BPS_PER_SIDE,
    )

    payload = {
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "development_start_utc": DEVELOPMENT_START_UTC,
        "development_end_utc_exclusive": DEVELOPMENT_END_UTC,
        "confirmation_data_loaded": False,
        "dataset_sha256": dataset_sha256,
        "bars": len(bars),
        "family": "mean_reversion",
        "parameters": {
            "lookback_bars": 20,
            "entry_sigma": 2.0,
            "exit_at_mean": True,
        },
        "costs": {
            "fee_bps_per_side": FEE_BPS_PER_SIDE,
            "slippage_bps_per_side": SLIPPAGE_BPS_PER_SIDE,
            "round_trip_bps": 4.0,
        },
        "result": {
            "final_return": result.final_return,
            "expectancy": result.expectancy,
            "profit_factor": result.profit_factor,
            "max_drawdown": result.max_drawdown,
            "trades": len(result.trades),
        },
        "classification": (
            "DEVELOPMENT_POSITIVE_CANDIDATE"
            if result.expectancy > 0 and result.profit_factor > 1.0 and len(result.trades) >= 30
            else "NO_POSITIVE_DEVELOPMENT_EFFECT"
        ),
    }
    (output / "mean_reversion_development_result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="research_artifacts/xagusd_mean_reversion_development")
    args = parser.parse_args()
    run(args.output_dir)


if __name__ == "__main__":
    main()
