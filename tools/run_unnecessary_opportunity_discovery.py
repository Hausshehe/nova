#!/usr/bin/env python3
"""Discover observable strata concentrated in unnecessary baseline requests.

This is a hypothesis-generation tool, not an adaptive-policy evaluator. It uses
completed future labels to describe the dataset after the fact. Any pattern
found here must be validated causally with walk-forward data before deployment.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.data import load_csv
from trading_research.market_monitor import MarketMonitor
from trading_research.strategy_escalation_bridge import evaluate_strategy_escalation
from trading_research.strategy_escalation_efficiency import _actionable_indices


def _tier_code(tier: str) -> int:
    return {"WEAK": 0, "DEVELOPING": 1, "STRONG": 2}.get(tier, -1)


def _reason_family(reason: str) -> str:
    if reason.startswith("strong strategy hint"):
        return "strong_strategy"
    if reason.startswith("developing strategy"):
        return "developing_strategy"
    if reason.startswith("new bar"):
        return "new_bar"
    if "price move" in reason:
        return "price_move"
    return "other"


def _features(bars, index: int) -> tuple[float, float, float]:
    fast_period, slow_period, lookback = 20, 50, 3
    if index + 1 < slow_period:
        return 0.0, 0.0, 0.0
    fast = sum(x.close for x in bars[index - fast_period + 1:index + 1]) / fast_period
    slow = sum(x.close for x in bars[index - slow_period + 1:index + 1]) / slow_period
    gap = abs(fast / slow - 1.0) * 10_000.0 if slow else 0.0
    start = max(0, index - lookback)
    momentum = abs(bars[index].close / bars[start].close - 1.0) * 10_000.0 if bars[start].close else 0.0
    if index >= lookback and start + 1 >= slow_period:
        start_fast = sum(x.close for x in bars[start - fast_period + 1:start + 1]) / fast_period
        start_slow = sum(x.close for x in bars[start - slow_period + 1:start + 1]) / slow_period
        start_gap = abs(start_fast / start_slow - 1.0) * 10_000.0 if start_slow else 0.0
        slope = gap - start_gap
    else:
        slope = 0.0
    return momentum, gap, abs(slope)


def _label(bars, index: int) -> bool | None:
    future = bars[index + 1:index + 5]
    if len(future) < 4 or index + 1 < 50:
        return None
    move = max(abs(x.close / bars[index].close - 1.0) * 10_000.0 for x in future)
    if move < 34.0:
        return False
    fast = sum(x.close for x in bars[index - 19:index + 1]) / 20
    slow = sum(x.close for x in bars[index - 49:index + 1]) / 50
    return fast != slow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()

    bars = tuple(load_csv(args.dataset))
    events = MarketMonitor().observe_history("EURUSD", "15m", bars)
    decisions = evaluate_strategy_escalation(bars, events)
    baseline = {d.index for d in decisions if d.request_ai or d.strategy_hint.request_ai}
    actionable = _actionable_indices(
        bars, future_bars=4, opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0, fast_period=20, slow_period=50,
    )

    groups: dict[tuple, list[int]] = defaultdict(list)
    unnecessary: set[int] = baseline - actionable
    for d in decisions:
        if d.index not in baseline or d.index < 50 or d.index + 4 >= len(bars):
            continue
        momentum, gap, slope = _features(bars, d.index)
        key = (
            d.strategy_hint.confidence_tier,
            _reason_family(d.reason),
            int(momentum // 10),
            int(gap // 10),
            int(slope // 10),
        )
        groups[key].append(d.index)

    ranked = []
    for key, indices in groups.items():
        total = len(indices)
        bad = len(set(indices) & unnecessary)
        if total < 8 or bad == 0:
            continue
        ranked.append({
            "tier": key[0],
            "reason_family": key[1],
            "momentum_bin_10bps": key[2],
            "gap_bin_10bps": key[3],
            "slope_bin_10bps": key[4],
            "candidates": total,
            "unnecessary": bad,
            "actionable": total - bad,
            "actionable_rate": (total - bad) / total,
            "unnecessary_rate": bad / total,
        })

    ranked.sort(key=lambda x: (-x["unnecessary_rate"], -x["unnecessary"], -x["candidates"]))
    payload = {
        "schema_version": 1,
        "dataset": args.dataset,
        "purpose": "post_hoc_hypothesis_discovery_only",
        "warning": "These full-sample strata use completed future labels for discovery. Do not deploy any rule from this output without causal walk-forward validation.",
        "baseline_candidates": len(baseline),
        "unnecessary_candidates": len(unnecessary),
        "top_unnecessary_strata": ranked[:30],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
