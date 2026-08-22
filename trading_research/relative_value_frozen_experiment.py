"""Frozen relative-value experiment.

Hypothesis: within predefined economically related asset pairs, the asset that
has outperformed its paired asset over a fixed causal lookback will continue to
outperform over the next fixed horizon after conservative transaction costs.

The pair list, lookback, horizon, split, costs, and promotion rules are frozen
before the final test. No parameter search, LLM reasoning, context selector, or
post-test tuning is used.
"""
from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from .data import load_csv

FUTURE_BARS = 4
LOOKBACK_BARS = 12
DEVELOPMENT_FRACTION = 0.80
ROUND_TRIP_COST_PER_LEG_BPS = 4.0
PAIR_ROUND_TRIP_COST_BPS = 8.0
MIN_TEST_TRADES_PER_PAIR = 40
MIN_PAIRS = 3
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 42

PAIRS = (
    ("EURUSD", "GBPUSD"),
    ("AUDUSD", "NZDUSD"),
    ("XAUUSD", "XAGUSD"),
    ("US500", "NAS100"),
    ("US30", "US500"),
)
TIMEFRAMES = ("1D", "4H")
ROOT = Path("data/research/universe_v2")
OUT = Path("data/research/relative_value")
SUMMARY = OUT / "summary.json"
RESULTS = OUT / "results.csv"


@dataclass(frozen=True)
class PairObservation:
    index: int
    relative_signal: int
    relative_return_bps: float


def _bars_by_timestamp(path: Path) -> dict:
    return {bar.timestamp: bar for bar in load_csv(path)}


def _aligned_series(left_path: Path, right_path: Path):
    left = _bars_by_timestamp(left_path)
    right = _bars_by_timestamp(right_path)
    timestamps = sorted(set(left) & set(right))
    return [left[t] for t in timestamps], [right[t] for t in timestamps]


def _observations(left, right):
    observations: list[PairObservation] = []
    start = LOOKBACK_BARS
    stop = len(left) - FUTURE_BARS
    for i in range(start, stop):
        left_now = left[i].close
        right_now = right[i].close
        left_then = left[i + FUTURE_BARS].close
        right_then = right[i + FUTURE_BARS].close
        left_past = left[i - LOOKBACK_BARS].close
        right_past = right[i - LOOKBACK_BARS].close
        if min(left_now, right_now, left_then, right_then, left_past, right_past) <= 0:
            continue

        left_trend = left_now / left_past - 1.0
        right_trend = right_now / right_past - 1.0
        signal = 1 if left_trend > right_trend else -1

        left_future = left_then / left_now - 1.0
        right_future = right_then / right_now - 1.0
        relative_future = (left_future - right_future) * 10_000.0
        signed = relative_future if signal == 1 else -relative_future
        observations.append(
            PairObservation(
                index=i,
                relative_signal=signal,
                relative_return_bps=signed - PAIR_ROUND_TRIP_COST_BPS,
            )
        )
    return observations


def _bootstrap_ci(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(values)
    means: list[float] = []
    for _ in range(BOOTSTRAP_SAMPLES):
        means.append(mean(rng.choice(values) for _ in range(n)))
    means.sort()
    return means[int(0.025 * BOOTSTRAP_SAMPLES)], means[int(0.975 * BOOTSTRAP_SAMPLES) - 1]


def _evaluate_pair(left, right) -> dict[str, object]:
    observations = _observations(left, right)
    split = int(len(observations) * DEVELOPMENT_FRACTION)
    development = observations[:split]
    test = observations[split:]
    test_returns = [x.relative_return_bps for x in test]
    low, high = _bootstrap_ci(test_returns)
    mean_net = mean(test_returns) if test_returns else 0.0
    return {
        "aligned_bars": len(observations) + LOOKBACK_BARS + FUTURE_BARS,
        "development_observations": len(development),
        "test_observations": len(test),
        "mean_test_net_bps": mean_net,
        "positive_test_rate": sum(x > 0 for x in test_returns) / len(test_returns) if test_returns else 0.0,
        "bootstrap_low": low,
        "bootstrap_high": high,
        "long_left_signals": sum(x.relative_signal == 1 for x in test),
        "long_right_signals": sum(x.relative_signal == -1 for x in test),
        "status": "PASS" if len(test) >= MIN_TEST_TRADES_PER_PAIR and mean_net > 0 and low > 0 else "FAIL",
    }


def run() -> dict[str, object]:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    pair_metrics = []

    for timeframe in TIMEFRAMES:
        for left_name, right_name in PAIRS:
            left_path = ROOT / f"{left_name}_{timeframe}.csv"
            right_path = ROOT / f"{right_name}_{timeframe}.csv"
            if not left_path.exists() or not right_path.exists():
                raise RuntimeError(f"missing_pair_dataset:{left_name}:{right_name}:{timeframe}")
            left, right = _aligned_series(left_path, right_path)
            if len(left) != len(right) or len(left) < 500:
                raise RuntimeError(f"insufficient_aligned_bars:{left_name}:{right_name}:{timeframe}:{len(left)}")
            metrics = _evaluate_pair(left, right)
            row = {"timeframe": timeframe, "left": left_name, "right": right_name, **metrics}
            rows.append(row)
            pair_metrics.append(row)

    eligible = [r for r in pair_metrics if r["test_observations"] >= MIN_TEST_TRADES_PER_PAIR]
    passing_pairs = [r for r in eligible if r["status"] == "PASS"]
    aggregate_returns = []
    for timeframe in TIMEFRAMES:
        for left_name, right_name in PAIRS:
            left_path = ROOT / f"{left_name}_{timeframe}.csv"
            right_path = ROOT / f"{right_name}_{timeframe}.csv"
            left, right = _aligned_series(left_path, right_path)
            observations = _observations(left, right)
            split = int(len(observations) * DEVELOPMENT_FRACTION)
            aggregate_returns.extend(x.relative_return_bps for x in observations[split:])

    aggregate_low, aggregate_high = _bootstrap_ci(aggregate_returns)
    aggregate_mean = mean(aggregate_returns) if aggregate_returns else 0.0
    passed = bool(
        len(passing_pairs) >= MIN_PAIRS
        and aggregate_mean > 0.0
        and aggregate_low > 0.0
    )

    summary = {
        "experiment": "relative_value_frozen",
        "hypothesis": "Within predefined related pairs, the recent outperformer will continue to outperform the recent underperformer over the next 4 bars after costs.",
        "status": "PASS" if passed else "FAIL",
        "pairs": PAIRS,
        "timeframes": TIMEFRAMES,
        "lookback_bars": LOOKBACK_BARS,
        "future_bars": FUTURE_BARS,
        "development_fraction": DEVELOPMENT_FRACTION,
        "pair_round_trip_cost_bps": PAIR_ROUND_TRIP_COST_BPS,
        "final_test_untouched_before_evaluation": True,
        "eligible_pair_evaluations": len(eligible),
        "passing_pair_evaluations": len(passing_pairs),
        "aggregate_test_observations": len(aggregate_returns),
        "aggregate_mean_net_bps": aggregate_mean,
        "aggregate_bootstrap_low": aggregate_low,
        "aggregate_bootstrap_high": aggregate_high,
        "minimum_test_observations_per_pair": MIN_TEST_TRADES_PER_PAIR,
        "minimum_passing_pair_evaluations": MIN_PAIRS,
        "results": rows,
        "kill_rule": "If the frozen final test fails, do not tune pair membership, lookback, horizon, costs, or signal direction within this relative-value hypothesis family; record failure and move to the next hypothesis.",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        fields = [k for k in rows[0]]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    run()
