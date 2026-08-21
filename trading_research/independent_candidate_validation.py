"""Independent validation of the two frozen screen-positive broader-campaign candidates.

This module deliberately does not search, rank, tune, or alter candidates. It evaluates
only the exact two contexts produced by the frozen 104-context campaign, using a new
calendar period that was outside the campaign's frozen 2010-2025 dataset snapshot.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Sequence

from .backtest import BacktestResult, run_long_flat
from .data import Bar, load_csv
from .broader_campaign_runner import breakout_volatility_signal_series, cross_market_signal_factory
from .dukascopy_history import DukascopyClient, write_csv

VALIDATION_START = "2026-01-01T00:00:00+00:00"
VALIDATION_END = "2026-08-20T00:00:00+00:00"
FEE_BPS = 1.0
SLIPPAGE_BPS = 1.0
BOOTSTRAP_BLOCK = 5
BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_SEED = 42
MIN_TRADES = 10
MIN_PF = 1.15

RAW_DIR = Path("data/research/independent_validation")
RESULTS_CSV = RAW_DIR / "candidate_results.csv"
SUMMARY_JSON = RAW_DIR / "candidate_summary.json"
MANIFEST_JSON = RAW_DIR / "manifest.json"

FROZEN_CANDIDATES = (
    {
        "asset_family": "INDEX",
        "instrument": "NAS100",
        "timeframe": "4H",
        "hypothesis_family": "breakout_volatility_expansion",
        "discovery_run_id": 32456926447,
        "discovery_test_expectancy": 0.0059253852441803955,
        "discovery_test_pf": 2.590167775656616,
        "discovery_test_trades": 45,
        "discovery_bootstrap_low": 0.0009401061101483668,
    },
    {
        "asset_family": "COMMODITY",
        "instrument": "XAGUSD",
        "timeframe": "4H",
        "hypothesis_family": "cross_market_relative_behavior",
        "discovery_run_id": 32456926447,
        "discovery_test_expectancy": 0.003531009373444449,
        "discovery_test_pf": 1.878923338408972,
        "discovery_test_trades": 165,
        "discovery_bootstrap_low": 0.0003657821949713342,
    },
)


@dataclass(frozen=True)
class CandidateValidationResult:
    asset_family: str
    instrument: str
    timeframe: str
    hypothesis_family: str
    validation_start: str
    validation_end: str
    bars: int
    trades: int
    final_return: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    bootstrap_low: float
    bootstrap_high: float
    status: str


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def moving_block_bootstrap_ci(
    returns: Sequence[float], *, block_length: int, samples: int, seed: int
) -> tuple[float, float]:
    if not returns:
        return 0.0, 0.0
    n = len(returns)
    block_length = min(block_length, n)
    starts = list(range(max(1, n - block_length + 1)))
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(samples):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.choice(starts)
            sample.extend(returns[start : start + block_length])
        sample = sample[:n]
        means.append(sum(sample) / n)
    means.sort()
    return means[int(samples * 0.025)], means[int(samples * 0.975) - 1]


def _status(result: BacktestResult, low: float) -> str:
    trades = len(result.trades)
    if trades < MIN_TRADES:
        return "FAIL_INSUFFICIENT_TRADES"
    if result.expectancy <= 0 or result.profit_factor < MIN_PF or low <= 0:
        return "FAIL"
    return "PASS"


def _download(instrument: str, timeframe: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{instrument}_{timeframe}.csv"
    candles = DukascopyClient().historical_prices(
        instrument=instrument,
        timeframe=timeframe,
        start_utc=VALIDATION_START,
        end_utc=VALIDATION_END,
        progress=lambda message: print(message, flush=True),
    )
    if len(candles) < 100:
        raise RuntimeError(f"insufficient_bars:{instrument}:{timeframe}:{len(candles)}")
    write_csv(candles, path)
    return path


def _verify_period(bars: Sequence[Bar]) -> None:
    start = _parse_timestamp(VALIDATION_START)
    end = _parse_timestamp(VALIDATION_END)
    if not bars:
        raise ValueError("validation_dataset_empty")
    if bars[0].timestamp < start:
        raise ValueError(f"validation_dataset_starts_too_early:{bars[0].timestamp.isoformat()}")
    if bars[-1].timestamp >= end:
        raise ValueError(f"validation_dataset_ends_too_late:{bars[-1].timestamp.isoformat()}")


def _run_candidate(candidate: dict[str, object], bars_by_instrument: dict[str, Sequence[Bar]]) -> CandidateValidationResult:
    focal = list(bars_by_instrument[candidate["instrument"]])
    family = str(candidate["hypothesis_family"])
    if family == "breakout_volatility_expansion":
        states = breakout_volatility_signal_series(focal)
        signal = lambda _, index: states[index]
    elif family == "cross_market_relative_behavior":
        signal = cross_market_signal_factory(bars_by_instrument, str(candidate["instrument"]))
    else:
        raise ValueError(f"unsupported_frozen_candidate_family:{family}")

    result = run_long_flat(
        focal,
        signal,
        fee_bps=FEE_BPS,
        slippage_bps=SLIPPAGE_BPS,
    )
    low, high = moving_block_bootstrap_ci(
        [trade.return_fraction for trade in result.trades],
        block_length=BOOTSTRAP_BLOCK,
        samples=BOOTSTRAP_SAMPLES,
        seed=BOOTSTRAP_SEED,
    )
    return CandidateValidationResult(
        asset_family=str(candidate["asset_family"]),
        instrument=str(candidate["instrument"]),
        timeframe=str(candidate["timeframe"]),
        hypothesis_family=family,
        validation_start=VALIDATION_START,
        validation_end=VALIDATION_END,
        bars=len(focal),
        trades=len(result.trades),
        final_return=result.final_return,
        expectancy=result.expectancy,
        profit_factor=result.profit_factor,
        max_drawdown=result.max_drawdown,
        bootstrap_low=low,
        bootstrap_high=high,
        status=_status(result, low),
    )


def run() -> dict[str, object]:
    # Fail closed if the frozen candidate set changes.
    expected_keys = {
        ("NAS100", "4H", "breakout_volatility_expansion"),
        ("XAGUSD", "4H", "cross_market_relative_behavior"),
    }
    actual_keys = {
        (str(item["instrument"]), str(item["timeframe"]), str(item["hypothesis_family"]))
        for item in FROZEN_CANDIDATES
    }
    if actual_keys != expected_keys:
        raise AssertionError(f"frozen_candidate_drift:{sorted(actual_keys)}")

    required = {"NAS100", "XAGUSD", "XAUUSD", "WTI"}
    paths = {instrument: _download(instrument, "4H") for instrument in sorted(required)}
    bars_by_instrument = {instrument: load_csv(path) for instrument, path in paths.items()}
    for bars in bars_by_instrument.values():
        _verify_period(bars)

    results = tuple(_run_candidate(candidate, bars_by_instrument) for candidate in FROZEN_CANDIDATES)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with RESULTS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)

    manifest = {
        instrument: {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bars": len(bars_by_instrument[instrument]),
            "start": bars_by_instrument[instrument][0].timestamp.isoformat(),
            "end": bars_by_instrument[instrument][-1].timestamp.isoformat(),
        }
        for instrument, path in paths.items()
    }
    MANIFEST_JSON.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    statuses = {result.status for result in results}
    overall = "PASS" if statuses == {"PASS"} else "FAIL"
    summary = {
        "overall_status": overall,
        "validation_start": VALIDATION_START,
        "validation_end": VALIDATION_END,
        "fee_bps_per_side": FEE_BPS,
        "slippage_bps_per_side": SLIPPAGE_BPS,
        "bootstrap_block": BOOTSTRAP_BLOCK,
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "min_trades": MIN_TRADES,
        "min_profit_factor": MIN_PF,
        "discovery_run_id": 32456926447,
        "candidate_count": len(results),
        "results": [asdict(result) for result in results],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    if overall != "PASS":
        raise SystemExit(2)
    return summary


if __name__ == "__main__":
    run()
