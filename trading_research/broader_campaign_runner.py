"""Deterministic execution of Nova's frozen 104-context broader campaign."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Callable, Sequence

from .backtest import BacktestResult, run_long_flat
from .data import Bar, DatasetSplit, chronological_split, load_csv
from .research_universe import ASSET_FAMILIES, ResearchContext, build_research_universe

DATA_DIR = Path("data/research/universe_v2")
MANIFEST_PATH = DATA_DIR / "manifest.json"
RESULTS_CSV = Path("data/research/broader_matrix_results.csv")
SUMMARY_JSON = Path("data/research/broader_matrix_summary.json")
REPORT_MD = Path("data/research/broader_matrix_report.md")
FEE_BPS = 1.0
SLIPPAGE_BPS = 1.0
BOOTSTRAP_BLOCK = 5
BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_SEED = 42
MIN_TEST_TRADES = 30
MIN_TEST_PF = 1.15


@dataclass(frozen=True)
class ContextResult:
    asset_family: str
    instrument: str
    timeframe: str
    hypothesis_family: str
    train_return: float
    train_expectancy: float
    train_pf: float
    train_max_dd: float
    train_trades: int
    validation_return: float
    validation_expectancy: float
    validation_pf: float
    validation_max_dd: float
    validation_trades: int
    test_return: float
    test_expectancy: float
    test_pf: float
    test_max_dd: float
    test_trades: int
    test_bootstrap_low: float
    test_bootstrap_high: float
    screen_positive: bool


@dataclass(frozen=True)
class DatasetRecord:
    instrument: str
    timeframe: str
    bars: tuple[Bar, ...]
    split: DatasetSplit


def _sma(bars: Sequence[Bar], end_index: int, period: int) -> float:
    return sum(bar.close for bar in bars[end_index - period + 1 : end_index + 1]) / period


def _std_population(bars: Sequence[Bar], end_index: int, period: int) -> float:
    values = [bar.close for bar in bars[end_index - period + 1 : end_index + 1]]
    mean = sum(values) / period
    return math.sqrt(sum((value - mean) ** 2 for value in values) / period)


def _true_range(bars: Sequence[Bar], index: int) -> float:
    if index == 0:
        return bars[index].high - bars[index].low
    previous_close = bars[index - 1].close
    return max(
        bars[index].high - bars[index].low,
        abs(bars[index].high - previous_close),
        abs(bars[index].low - previous_close),
    )


def momentum_signal_series(bars: Sequence[Bar]) -> list[bool]:
    states = [False] * len(bars)
    for index in range(49, len(bars)):
        states[index] = _sma(bars, index, 20) >= _sma(bars, index, 50)
    return states


def mean_reversion_signal_series(bars: Sequence[Bar]) -> list[bool]:
    """Causal 20-bar two-sigma mean reversion using prior completed bars only."""
    states = [False] * len(bars)
    in_position = False
    for index in range(len(bars)):
        if index < 20:
            continue
        mean = _sma(bars, index - 1, 20)
        std = _std_population(bars, index - 1, 20)
        if not in_position and bars[index].close <= mean - 2.0 * std:
            in_position = True
        elif in_position and bars[index].close >= mean:
            in_position = False
        states[index] = in_position
    return states


def breakout_volatility_signal_series(bars: Sequence[Bar]) -> list[bool]:
    states = [False] * len(bars)
    in_position = False
    for index in range(len(bars)):
        if index < 59:
            continue
        prior_high = max(bar.high for bar in bars[index - 55 : index])
        prior_low = min(bar.low for bar in bars[index - 20 : index])
        current_atr = sum(_true_range(bars, j) for j in range(index - 19, index + 1)) / 20.0
        previous_atr = sum(_true_range(bars, j) for j in range(index - 39, index - 19)) / 20.0
        if not in_position and bars[index].close > prior_high and current_atr >= previous_atr:
            in_position = True
        elif in_position and bars[index].close < prior_low:
            in_position = False
        states[index] = in_position
    return states


def _aligned_cross_section(bars_by_instrument: dict[str, Sequence[Bar]]) -> dict[str, list[Bar]]:
    timestamp_sets = [set(bar.timestamp for bar in bars) for bars in bars_by_instrument.values()]
    if not timestamp_sets:
        return {}
    common_timestamps = sorted(set.intersection(*timestamp_sets))
    return {
        instrument: [bar for bar in bars if bar.timestamp in common_timestamps]
        for instrument, bars in bars_by_instrument.items()
    }


def cross_market_signal_factory(
    bars_by_instrument: dict[str, Sequence[Bar]],
    focal_instrument: str,
) -> Callable[[Sequence[Bar], int], bool]:
    aligned = _aligned_cross_section(bars_by_instrument)
    focal = aligned.get(focal_instrument, [])
    desired: dict = {}
    in_position = False
    for index in range(20, len(focal)):
        returns: dict[str, float] = {}
        timestamp = focal[index].timestamp
        for instrument, series in aligned.items():
            if index >= len(series) or series[index - 20].close <= 0:
                continue
            returns[instrument] = series[index].close / series[index - 20].close - 1.0
        if len(returns) < 3:
            desired[timestamp] = in_position
            continue
        med = median(returns.values())
        mad = median(abs(value - med) for value in returns.values())
        focal_return = returns[focal_instrument]
        if not in_position and focal_return > med + mad:
            in_position = True
        elif in_position and focal_return <= med:
            in_position = False
        desired[timestamp] = in_position
    return lambda bars, index: bool(desired.get(bars[index].timestamp, False))


def moving_block_bootstrap_ci(
    returns: Sequence[float],
    *,
    block_length: int = BOOTSTRAP_BLOCK,
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    if not returns:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(returns)
    block_length = min(block_length, n)
    starts = list(range(max(1, n - block_length + 1)))
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


def _metrics(result: BacktestResult) -> tuple[float, float, float, float, int]:
    return result.final_return, result.expectancy, result.profit_factor, result.max_drawdown, len(result.trades)


def _expected_pairs() -> set[tuple[str, str]]:
    return {
        (instrument, timeframe)
        for instruments in ASSET_FAMILIES.values()
        for instrument in instruments
        for timeframe in ("1D", "4H")
    }


def verify_manifest() -> dict[tuple[str, str], dict]:
    if not MANIFEST_PATH.exists():
        raise ValueError("manifest_missing")
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("manifest_not_array")
    expected = _expected_pairs()
    actual = {(item.get("instrument"), item.get("timeframe")) for item in payload if isinstance(item, dict)}
    if len(payload) != 26 or actual != expected:
        raise ValueError(f"manifest_context_mismatch:entries={len(payload)}")
    verified: dict[tuple[str, str], dict] = {}
    for item in payload:
        instrument = item["instrument"]
        timeframe = item["timeframe"]
        path = DATA_DIR / f"{instrument}_{timeframe}.csv"
        if not path.exists():
            raise ValueError(f"dataset_missing:{instrument}:{timeframe}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"dataset_hash_mismatch:{instrument}:{timeframe}")
        bars = int(item["bars"])
        if bars < 100:
            raise ValueError(f"dataset_too_small:{instrument}:{timeframe}:{bars}")
        verified[(instrument, timeframe)] = item
    return verified


def _load_records() -> dict[tuple[str, str], DatasetRecord]:
    verify_manifest()
    records: dict[tuple[str, str], DatasetRecord] = {}
    for instruments in ASSET_FAMILIES.values():
        for instrument in instruments:
            for timeframe in ("1D", "4H"):
                path = DATA_DIR / f"{instrument}_{timeframe}.csv"
                bars = tuple(load_csv(path))
                if len(bars) < 100:
                    raise ValueError(f"insufficient_bars:{instrument}:{timeframe}:{len(bars)}")
                records[(instrument, timeframe)] = DatasetRecord(
                    instrument, timeframe, bars, chronological_split(bars)
                )
    if len(records) != 26:
        raise ValueError(f"dataset_count_mismatch:{len(records)}")
    return records


def _single_family_signal(family: str, bars: Sequence[Bar]) -> Callable[[Sequence[Bar], int], bool]:
    if family == "momentum_continuation":
        states = momentum_signal_series(bars)
    elif family == "mean_reversion":
        states = mean_reversion_signal_series(bars)
    elif family == "breakout_volatility_expansion":
        states = breakout_volatility_signal_series(bars)
    else:
        raise ValueError(f"unsupported_single_market_family:{family}")
    return lambda _, index: states[index]


def evaluate_context(context: ResearchContext, records: dict[tuple[str, str], DatasetRecord]) -> ContextResult:
    focal = records[(context.instrument, context.timeframe)]
    family_records = {
        instrument: records[(instrument, context.timeframe)]
        for instrument in ASSET_FAMILIES[context.asset_family]
    }
    results: dict[str, BacktestResult] = {}
    for segment_name in ("train", "validation", "test"):
        segment_bars = getattr(focal.split, segment_name)
        if context.hypothesis_family == "cross_market_relative_behavior":
            split_bars_by_instrument = {
                instrument: getattr(record.split, segment_name)
                for instrument, record in family_records.items()
            }
            signal = cross_market_signal_factory(split_bars_by_instrument, context.instrument)
        else:
            signal = _single_family_signal(context.hypothesis_family, segment_bars)
        results[segment_name] = run_long_flat(
            segment_bars,
            signal,
            fee_bps=FEE_BPS,
            slippage_bps=SLIPPAGE_BPS,
        )

    train = _metrics(results["train"])
    validation = _metrics(results["validation"])
    test = _metrics(results["test"])
    bootstrap_low, bootstrap_high = moving_block_bootstrap_ci(
        [trade.return_fraction for trade in results["test"].trades]
    )
    screen_positive = (
        test[4] >= MIN_TEST_TRADES
        and test[2] >= MIN_TEST_PF
        and test[1] > 0
        and validation[1] > 0
        and bootstrap_low > 0
    )
    return ContextResult(
        context.asset_family,
        context.instrument,
        context.timeframe,
        context.hypothesis_family,
        train[0], train[1], train[2], train[3], train[4],
        validation[0], validation[1], validation[2], validation[3], validation[4],
        test[0], test[1], test[2], test[3], test[4],
        bootstrap_low, bootstrap_high, screen_positive,
    )


def _write_results(results: Sequence[ContextResult]) -> None:
    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)


def _family_summary(results: Sequence[ContextResult]) -> dict[str, dict[str, int | float]]:
    summary: dict[str, dict[str, int | float]] = {}
    for family in sorted({result.hypothesis_family for result in results}):
        subset = [result for result in results if result.hypothesis_family == family]
        candidates = [result for result in subset if result.screen_positive]
        summary[family] = {
            "contexts": len(subset),
            "screen_positive_contexts": len(candidates),
            "test_expectancy_mean": sum(r.test_expectancy for r in subset) / len(subset),
            "test_expectancy_median": median(r.test_expectancy for r in subset),
            "test_positive_expectancy_contexts": sum(r.test_expectancy > 0 for r in subset),
            "test_trades_ge_30": sum(r.test_trades >= MIN_TEST_TRADES for r in subset),
        }
    return summary


def run_campaign() -> dict:
    universe = build_research_universe()
    if len(universe) != 104:
        raise ValueError(f"context_count_mismatch:{len(universe)}")
    records = _load_records()
    results = tuple(evaluate_context(context, records) for context in universe)
    _write_results(results)
    family_summary = _family_summary(results)
    payload = {
        "contexts": len(results),
        "datasets": len(records),
        "cost_fee_bps_per_side": FEE_BPS,
        "cost_slippage_bps_per_side": SLIPPAGE_BPS,
        "bootstrap_block": BOOTSTRAP_BLOCK,
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "screen_positive_total": sum(result.screen_positive for result in results),
        "family_summary": family_summary,
        "decision_checkpoint": "STOP_AND_REVIEW",
        "results_csv": str(RESULTS_CSV),
    }
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Nova Broader Campaign Matrix",
        "",
        f"Contexts evaluated: {len(results)} / 104",
        f"Datasets: {len(records)} / 26",
        f"Screen-positive contexts: {payload['screen_positive_total']}",
        "",
        "## Family summary",
        "",
        "| Family | Contexts | Screen-positive | Median test expectancy | Positive-test contexts | Test contexts >=30 trades |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for family, values in family_summary.items():
        lines.append(
            f"| {family} | {values['contexts']} | {values['screen_positive_contexts']} | "
            f"{values['test_expectancy_median']:.8f} | {values['test_positive_expectancy_contexts']} | {values['test_trades_ge_30']} |"
        )
    lines += [
        "",
        "## Decision checkpoint",
        "",
        "The fixed matrix is complete. STOP. Review the result, uncertainty, breadth, and evidence quality and classify the campaign as YES, NO, or INCONCLUSIVE.",
        "",
        "A screen-positive context is exploratory only and is not promotion evidence.",
    ]
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    payload = run_campaign()
    print(f"contexts={payload['contexts']}")
    print(f"datasets={payload['datasets']}")
    print(f"screen_positive_total={payload['screen_positive_total']}")
    print(f"results={RESULTS_CSV}")
    print(f"summary={SUMMARY_JSON}")
    print("DECISION_CHECKPOINT=STOP_AND_REVIEW")
