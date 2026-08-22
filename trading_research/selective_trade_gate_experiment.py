"""Frozen selective-trade-gate experiment.

Hypothesis: a causal, walk-forward trade-quality gate can improve a fixed
20/50-SMA long/flat signal by abstaining only when the historical conditional
net outcome of the same signal state is not favorable.

The gate is fixed before final evaluation. It learns only from observations
whose complete future outcome is already known. It does not choose the base
strategy, optimize parameters, or use LLM reasoning.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from .data import load_csv

FUTURE_BARS = 4
FEE_BPS_PER_SIDE = 1.0
SLIPPAGE_BPS_PER_SIDE = 1.0
ROUND_TRIP_COST_BPS = 4.0
FAST_PERIOD = 20
SLOW_PERIOD = 50
MOMENTUM_LOOKBACK = 3
GAP_BUCKET_BPS = 5.0
MOMENTUM_BUCKET_BPS = 10.0
MIN_STATE_SAMPLES = 40
DEVELOPMENT_FRACTION = 0.80
MIN_TEST_TRADES_PER_CONTEXT = 20
MIN_RETENTION_RATIO = 0.70
MIN_CONTEXTS_IMPROVED = 13
MIN_AGGREGATE_IMPROVEMENT_BPS_PER_ELIGIBLE_BAR = 0.0

ROOT = Path("data/research/selective_trade_gate")
SUMMARY = ROOT / "summary.json"
RESULTS = ROOT / "results.csv"


@dataclass(frozen=True)
class TradeObservation:
    index: int
    state: tuple[int, int]
    base_return_bps: float


def _sma(bars, end: int, period: int) -> float:
    return sum(x.close for x in bars[end - period + 1 : end + 1]) / period


def _state(bars, index: int) -> tuple[int, int] | None:
    if index + 1 < SLOW_PERIOD:
        return None
    fast = _sma(bars, index, FAST_PERIOD)
    slow = _sma(bars, index, SLOW_PERIOD)
    if slow == 0:
        return None
    gap = abs(fast / slow - 1.0) * 10_000.0
    start = index - MOMENTUM_LOOKBACK
    momentum = (bars[index].close / bars[start].close - 1.0) * 10_000.0 if bars[start].close else 0.0
    return int(gap // GAP_BUCKET_BPS), int(momentum // MOMENTUM_BUCKET_BPS)


def _base_signal(bars, index: int) -> bool:
    if index + 1 < SLOW_PERIOD:
        return False
    return _sma(bars, index, FAST_PERIOD) >= _sma(bars, index, SLOW_PERIOD)


def _observation(bars, index: int) -> TradeObservation | None:
    if index + FUTURE_BARS >= len(bars):
        return None
    state = _state(bars, index)
    if state is None or not _base_signal(bars, index):
        return None
    raw = (bars[index + FUTURE_BARS].close / bars[index].close - 1.0) * 10_000.0
    return TradeObservation(index, state, raw - ROUND_TRIP_COST_BPS)


def _evaluate_context(bars):
    split = int(len(bars) * DEVELOPMENT_FRACTION)
    observations = [o for i in range(split) if (o := _observation(bars, i)) is not None]
    state_returns: dict[tuple[int, int], list[float]] = {}
    for obs in observations:
        state_returns.setdefault(obs.state, []).append(obs.base_return_bps)

    test: list[TradeObservation] = []
    for i in range(split, len(bars) - FUTURE_BARS):
        obs = _observation(bars, i)
        if obs is not None:
            test.append(obs)

    gated = [obs for obs in test if len(state_returns.get(obs.state, ())) >= MIN_STATE_SAMPLES and mean(state_returns[obs.state]) > 0.0]
    baseline_returns = [obs.base_return_bps for obs in test]
    gated_returns = [obs.base_return_bps for obs in gated]
    gated_indexes = {obs.index for obs in gated}

    # Economic contribution per eligible test bar. A skipped base trade contributes zero.
    baseline_total = sum(baseline_returns)
    gated_total = sum(obs.base_return_bps for obs in gated)
    eligible_bars = max(1, len(bars) - split - FUTURE_BARS)
    baseline_per_bar = baseline_total / eligible_bars
    gated_per_bar = gated_total / eligible_bars
    improvement_per_bar = gated_per_bar - baseline_per_bar

    # Paired block bootstrap over the eligible test bars' contributions.
    contributions = []
    baseline_by_index = {obs.index: obs.base_return_bps for obs in test}
    for i in range(split, len(bars) - FUTURE_BARS):
        base = baseline_by_index.get(i, 0.0)
        gate = next((obs.base_return_bps for obs in gated if obs.index == i), 0.0)
        contributions.append(gate - base)
    low, high = _bootstrap_mean_ci(contributions)

    return {
        "development_bars": split,
        "test_bars": len(bars) - split,
        "development_states": len(state_returns),
        "test_base_trades": len(test),
        "test_gated_trades": len(gated),
        "retention_ratio": len(gated) / len(test) if test else 0.0,
        "baseline_mean_net_bps": mean(baseline_returns) if baseline_returns else 0.0,
        "gated_mean_net_bps": mean(gated_returns) if gated_returns else 0.0,
        "baseline_total_net_bps": baseline_total,
        "gated_total_net_bps": gated_total,
        "improvement_mean_net_bps_per_trade": (mean(gated_returns) - mean(baseline_returns)) if gated_returns and baseline_returns else 0.0,
        "improvement_mean_net_bps_per_eligible_bar": improvement_per_bar,
        "paired_bootstrap_low": low,
        "paired_bootstrap_high": high,
        "contexts": sorted({obs.state for obs in test}),
        "gated_indexes": sorted(gated_indexes),
    }


def _bootstrap_mean_ci(values: list[float], samples: int = 2000) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    # Deterministic LCG: no external dependency and reproducible evidence.
    seed = 42
    n = len(values)
    means = []
    for _ in range(samples):
        total = 0.0
        for _ in range(n):
            seed = (1664525 * seed + 1013904223) & 0xFFFFFFFF
            total += values[seed % n]
        means.append(total / n)
    means.sort()
    return means[int(0.025 * samples)], means[int(0.975 * samples) - 1]


def run() -> dict[str, object]:
    ROOT.mkdir(parents=True, exist_ok=True)
    results = []
    aggregate_base: list[float] = []
    aggregate_gate: list[float] = []

    universe = []
    root = Path("data/research/universe_v2")
    for path in sorted(root.glob("*.csv")):
        stem = path.stem
        parts = stem.split("_")
        if len(parts) != 2:
            continue
        universe.append((parts[0], parts[1], path))

    if len(universe) != 26:
        raise RuntimeError(f"expected_26_contexts:{len(universe)}")

    for instrument, timeframe, path in universe:
        bars = load_csv(path)
        metrics = _evaluate_context(bars)
        results.append({"instrument": instrument, "timeframe": timeframe, **metrics})
        # Reconstruct per-bar totals from aggregate counts for the summary only.
        aggregate_base.append(metrics["baseline_total_net_bps"])
        aggregate_gate.append(metrics["gated_total_net_bps"])

    contexts_eligible = [r for r in results if r["test_base_trades"] >= MIN_TEST_TRADES_PER_CONTEXT]
    improved_contexts = sum(r["gated_mean_net_bps"] > r["baseline_mean_net_bps"] for r in contexts_eligible)
    total_base = sum(aggregate_base)
    total_gate = sum(aggregate_gate)
    total_trades_base = sum(r["test_base_trades"] for r in contexts_eligible)
    total_trades_gate = sum(r["test_gated_trades"] for r in contexts_eligible)
    retention = total_trades_gate / total_trades_base if total_trades_base else 0.0
    aggregate_improvement = total_gate - total_base

    # PASS requires positive gating contribution, positive total improvement,
    # adequate retention, and majority context-level improvement.
    passed = bool(
        contexts_eligible
        and total_gate > 0
        and aggregate_improvement > MIN_AGGREGATE_IMPROVEMENT_BPS_PER_ELIGIBLE_BAR
        and retention >= MIN_RETENTION_RATIO
        and improved_contexts >= MIN_CONTEXTS_IMPROVED
    )

    summary = {
        "experiment": "selective_trade_gate",
        "hypothesis": "A causal walk-forward gate can improve a fixed 20/50-SMA long/flat signal by abstaining from historically unfavorable state-action combinations.",
        "status": "PASS" if passed else "FAIL",
        "contexts": 26,
        "development_fraction": DEVELOPMENT_FRACTION,
        "final_test_untouched_before_evaluation": True,
        "future_bars": FUTURE_BARS,
        "transaction_cost_bps_round_trip": ROUND_TRIP_COST_BPS,
        "fixed_base_rule": "20-SMA >= 50-SMA; long/flat",
        "gate_rule": "state = abs(20/50 SMA gap bucket 5bps, signed 3-bar momentum bucket 10bps); require >=40 completed development trades in state and historical mean net outcome > 0; otherwise abstain",
        "minimum_test_trades_per_context": MIN_TEST_TRADES_PER_CONTEXT,
        "minimum_retention_ratio": MIN_RETENTION_RATIO,
        "minimum_contexts_improved": MIN_CONTEXTS_IMPROVED,
        "eligible_contexts": len(contexts_eligible),
        "contexts_improved": improved_contexts,
        "baseline_test_trades": total_trades_base,
        "gated_test_trades": total_trades_gate,
        "retention_ratio": retention,
        "baseline_total_net_bps": total_base,
        "gated_total_net_bps": total_gate,
        "aggregate_improvement_net_bps": aggregate_improvement,
        "results": [{k: v for k, v in r.items() if k != "gated_indexes"} for r in results],
        "kill_rule": "If the frozen final test fails, do not tune the state buckets, minimum samples, confidence rule, or base signal within this hypothesis family; record failure and move to the next hypothesis.",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with RESULTS.open("w", newline="", encoding="utf-8") as f:
        if results:
            fields = [k for k in results[0] if k != "contexts" and k != "gated_indexes"]
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in results:
                writer.writerow({k: row.get(k) for k in fields})
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    run()
