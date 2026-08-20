"""Pre-registered Experiment 2B: momentum confirmation on 2026 data only."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Sequence

import requests

from .backtest import BacktestResult, run_long_flat
from .broader_campaign_runner import momentum_signal_series, moving_block_bootstrap_ci
from .data import Bar, load_csv
from .dukascopy_history import DukascopyClient, INSTRUMENTS, TIMEFRAMES, write_csv
from .research_universe import ASSET_FAMILIES

START_UTC = "2026-01-01T00:00:00+00:00"
END_UTC = "2026-08-20T23:59:59+00:00"
FEE_BPS = 1.0
SLIPPAGE_BPS = 1.0
BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_SEED = 42
MIN_CONTEXTS = 26
MIN_POSITIVE_CONTEXTS = 13

ROOT = Path("data/research/experiment2b_momentum_confirmation")
RESULTS_CSV = ROOT / "momentum_confirmation_results.csv"
SUMMARY_JSON = ROOT / "momentum_confirmation_summary.json"
REPORT_MD = ROOT / "momentum_confirmation_report.md"


@dataclass(frozen=True)
class ConfirmationResult:
    instrument: str
    timeframe: str
    bars: int
    final_return: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    trades: int
    bootstrap_low: float
    bootstrap_high: float


def _expected_pairs() -> set[tuple[str, str]]:
    return {
        (instrument, timeframe)
        for family in ASSET_FAMILIES.values()
        for instrument in family
        for timeframe in TIMEFRAMES
    }


def _native_path(instrument: str, timeframe: str) -> Path:
    return ROOT / f"{instrument}_{timeframe}.csv"


def _download_native(instrument: str, timeframe: str) -> list[dict]:
    candles = DukascopyClient().historical_prices(
        instrument=instrument,
        timeframe=timeframe,
        start_utc=START_UTC,
        end_utc=END_UTC,
    )
    if not candles:
        raise ValueError(f"empty_native_dataset:{instrument}:{timeframe}")
    return candles


def _download_wti_yahoo() -> list[Bar]:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/CL=F"
    start = int(datetime.fromisoformat(START_UTC).timestamp())
    end = int(datetime.fromisoformat(END_UTC).timestamp()) + 1
    response = requests.get(
        url,
        params={"period1": start, "period2": end, "interval": "1d", "events": "history", "includeAdjustedClose": "true"},
        headers={"User-Agent": "Mozilla/5.0 (Nova-Experiment2B/1.0)"},
        timeout=60,
    )
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    rows: list[Bar] = []
    for index, ts in enumerate(timestamps):
        values = {key: quote[key][index] for key in ("open", "high", "low", "close", "volume")}
        if any(values[key] is None for key in ("open", "high", "low", "close")):
            continue
        timestamp = datetime.fromtimestamp(ts, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        bar = Bar(timestamp, float(values["open"]), float(values["high"]), float(values["low"]), float(values["close"]), float(values["volume"] or 0.0))
        bar.validate()
        rows.append(bar)
    if not rows:
        raise ValueError("empty_yahoo_wti_dataset")
    return rows


def _write_native(instrument: str, timeframe: str, candles: Sequence) -> Path:
    path = _native_path(instrument, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(candles, path)
    return path


def _write_wti() -> Path:
    path = _native_path("WTI", "1D")
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _download_wti_yahoo()
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("timestamp,open,high,low,close,volume\n")
        for bar in rows:
            handle.write(f"{bar.timestamp.isoformat()},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume}\n")
    return path


def _metrics(result: BacktestResult) -> tuple[float, float, float, float, int]:
    return result.final_return, result.expectancy, result.profit_factor, result.max_drawdown, len(result.trades)


def _bootstrap_context_mean(values: Sequence[float], *, samples: int = BOOTSTRAP_SAMPLES, seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []
    for _ in range(samples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    return means[int(samples * 0.025)], means[int(samples * 0.975) - 1]


def _collect_results() -> list[ConfirmationResult]:
    expected = _expected_pairs()
    if len(expected) != 26:
        raise ValueError(f"context_count_mismatch:{len(expected)}")
    results: list[ConfirmationResult] = []
    for instrument, timeframe in sorted(expected):
        path = _native_path(instrument, timeframe)
        bars = load_csv(path)
        if not bars:
            raise ValueError(f"empty_dataset:{instrument}:{timeframe}")
        signal_states = momentum_signal_series(bars)
        signal = lambda _, index, states=signal_states: states[index]
        backtest = run_long_flat(bars, signal, fee_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS)
        metrics = _metrics(backtest)
        low, high = moving_block_bootstrap_ci(
            [trade.return_fraction for trade in backtest.trades],
            samples=BOOTSTRAP_SAMPLES,
            seed=BOOTSTRAP_SEED,
        )
        results.append(ConfirmationResult(instrument, timeframe, len(bars), *metrics, low, high))
    return results


def run() -> dict:
    ROOT.mkdir(parents=True, exist_ok=True)
    for instrument, timeframe in sorted(_expected_pairs()):
        if instrument == "WTI" and timeframe == "1D":
            _write_wti()
        else:
            _write_native(instrument, timeframe, _download_native(instrument, timeframe))

    results = _collect_results()
    expectancies = [result.expectancy for result in results]
    positive_contexts = sum(value > 0 for value in expectancies)
    context_mean = sum(expectancies) / len(expectancies)
    context_ci_low, context_ci_high = _bootstrap_context_mean(expectancies)

    all_trade_returns: list[float] = []
    for instrument, timeframe in sorted(_expected_pairs()):
        bars = load_csv(_native_path(instrument, timeframe))
        signal_states = momentum_signal_series(bars)
        signal = lambda _, index, states=signal_states: states[index]
        backtest = run_long_flat(bars, signal, fee_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS)
        all_trade_returns.extend(trade.return_fraction for trade in backtest.trades)
    pooled_low, pooled_high = moving_block_bootstrap_ci(all_trade_returns, samples=BOOTSTRAP_SAMPLES, seed=BOOTSTRAP_SEED)

    confirmed = (
        len(results) == MIN_CONTEXTS
        and positive_contexts >= MIN_POSITIVE_CONTEXTS
        and median(expectancies) > 0
        and context_ci_low > 0
        and pooled_low > 0
    )

    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)

    summary = {
        "experiment": "Experiment 2B - Momentum Confirmation",
        "rules_frozen": "20-SMA >= 50-SMA; long/flat; 1 bps fee + 1 bps slippage per side",
        "data_start_utc": START_UTC,
        "data_end_utc": END_UTC,
        "contexts": len(results),
        "positive_contexts": positive_contexts,
        "positive_context_fraction": positive_contexts / len(results),
        "median_context_expectancy": median(expectancies),
        "mean_context_expectancy": context_mean,
        "context_bootstrap_low": context_ci_low,
        "context_bootstrap_high": context_ci_high,
        "pooled_trade_bootstrap_low": pooled_low,
        "pooled_trade_bootstrap_high": pooled_high,
        "confirmation_criteria": {
            "all_26_contexts_present": True,
            "positive_contexts_at_least_13": positive_contexts >= MIN_POSITIVE_CONTEXTS,
            "median_context_expectancy_positive": median(expectancies) > 0,
            "context_bootstrap_low_positive": context_ci_low > 0,
            "pooled_trade_bootstrap_low_positive": pooled_low > 0,
        },
        "classification": "CONFIRMED" if confirmed else "NOT_CONFIRMED",
        "results_sha256": hashlib.sha256(RESULTS_CSV.read_bytes()).hexdigest(),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_MD.write_text(
        "# Experiment 2B — Momentum Confirmation\n\n"
        f"Window: {START_UTC} through {END_UTC}\n\n"
        f"Contexts: {len(results)}/26\n\n"
        f"Positive contexts: {positive_contexts}/26 ({positive_contexts/len(results):.1%})\n\n"
        f"Median context expectancy: {median(expectancies):.8f}\n\n"
        f"Context bootstrap 95% CI: [{context_ci_low:.8f}, {context_ci_high:.8f}]\n\n"
        f"Pooled trade bootstrap 95% CI: [{pooled_low:.8f}, {pooled_high:.8f}]\n\n"
        f"Classification: **{summary['classification']}**\n\n"
        "The classification criteria were frozen before the 2026 data were downloaded.\n",
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    payload = run()
    print(json.dumps(payload, indent=2, sort_keys=True))
