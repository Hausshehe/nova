#!/usr/bin/env python3
"""Walk-forward validation for conservative candidate-risk filtering."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.data import load_csv
from trading_research.market_monitor import MarketMonitor
from trading_research.strategy_escalation_bridge import evaluate_strategy_escalation
from trading_research.strategy_escalation_efficiency import _actionable_indices, _precision

THRESHOLDS = (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)
RECALL_FLOOR = 0.98
MIN_SAMPLES = 20
WIDTH = 25.0
HORIZON = 4


def _tier_code(tier: str) -> int:
    return {"WEAK": 0, "DEVELOPING": 1, "STRONG": 2}.get(tier, -1)


def _reason_family(reason: str) -> int:
    if reason.startswith("strong strategy hint"):
        return 1
    if reason.startswith("developing strategy"):
        return 2
    if reason.startswith("new bar"):
        return 3
    if "price move" in reason:
        return 4
    return 0


def _features(bars, index: int):
    fast_period = 20
    slow_period = 50
    lookback = 3
    if index + 1 < slow_period:
        return 0.0, 0.0, 0.0
    fast = sum(x.close for x in bars[index-fast_period+1:index+1]) / fast_period
    slow = sum(x.close for x in bars[index-slow_period+1:index+1]) / slow_period
    gap = abs(fast / slow - 1.0) * 10_000.0 if slow else 0.0
    start = max(0, index - lookback)
    momentum = abs(bars[index].close / bars[start].close - 1.0) * 10_000.0 if bars[start].close else 0.0
    slope = 0.0
    if index >= lookback and start + 1 >= slow_period:
        start_fast = sum(x.close for x in bars[start-fast_period+1:start+1]) / fast_period
        start_slow = sum(x.close for x in bars[start-slow_period+1:start+1]) / slow_period
        start_gap = abs(start_fast / start_slow - 1.0) * 10_000.0 if start_slow else 0.0
        slope = gap - start_gap
    return momentum, gap, slope


def _bucket(bars, index: int, context, *, width: float):
    momentum, gap, slope = _features(bars, index)
    tier, reason = context.get(index, (-1, -1))
    return (int(momentum // width), int(gap // width), int(abs(slope) // width), tier, reason)


def _metrics(bars, indices, actionable):
    reviewed = len(indices & actionable)
    precision, justified = _precision(bars, indices, future_bars=HORIZON, opportunity_move_bps=30.0)
    return {
        "ai_requests": len(indices),
        "actionable_reviewed": reviewed,
        "actionable_recall": reviewed / len(actionable) if actionable else 0.0,
        "opportunity_precision": precision,
        "not_actionable_requests": len(indices - actionable),
        "unnecessary_ai_requests_legacy_precision_definition": max(0, len(indices) - justified),
    }


def _evaluate_segment(bars, baseline, context, start, end, *, history_bars=None):
    """Evaluate a segment using only history ending before its first decision."""
    train_end = start if history_bars is None else min(start, history_bars)
    history = defaultdict(lambda: deque(maxlen=500))

    training_actionable = _actionable_indices(
        bars[:train_end],
        future_bars=HORIZON,
        opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0,
        fast_period=20,
        slow_period=50,
    )
    for label_index in sorted(training_actionable | (baseline & set(range(train_end)))):
        if label_index < 0 or label_index + HORIZON >= train_end:
            continue
        if label_index not in baseline:
            continue
        history[_bucket(bars, label_index, context, width=WIDTH)].append(label_index in training_actionable)

    # Evaluate only decisions whose complete future horizon is inside this segment.
    segment_end = max(start, end - HORIZON)
    full_segment_actionable = _actionable_indices(
        bars[:end],
        future_bars=HORIZON,
        opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0,
        fast_period=20,
        slow_period=50,
    )
    actionable_segment = {idx for idx in full_segment_actionable if start <= idx < segment_end}
    evaluated_indices = set(range(start, segment_end))

    selected_by_threshold = {threshold: set() for threshold in THRESHOLDS}
    for index in evaluated_indices:
        if index not in baseline:
            continue
        probabilities = []
        bucket = _bucket(bars, index, context, width=WIDTH)
        if len(history[bucket]) >= MIN_SAMPLES:
            probabilities.append(sum(history[bucket]) / len(history[bucket]))
        ctx = context.get(index)
        if ctx is not None:
            broader = [v for key, vals in history.items() if key[3:] == ctx for v in vals]
            tier_vals = [v for key, vals in history.items() if key[3] == ctx[0] for v in vals]
            if len(broader) >= MIN_SAMPLES:
                probabilities.append(sum(broader) / len(broader))
            if len(tier_vals) >= MIN_SAMPLES:
                probabilities.append(sum(tier_vals) / len(tier_vals))
        p_actionable = min(probabilities) if probabilities else None
        for threshold in THRESHOLDS:
            if p_actionable is None or p_actionable >= threshold:
                selected_by_threshold[threshold].add(index)

    results = {}
    for threshold, selected in selected_by_threshold.items():
        recall = len(selected & actionable_segment) / len(actionable_segment) if actionable_segment else 0.0
        effective = selected
        results[threshold] = {
            "accepted": recall >= RECALL_FLOOR,
            "metrics": _metrics(bars, effective, actionable_segment),
            "suppressed": len((baseline & evaluated_indices) - selected),
            "evaluated_bars": len(evaluated_indices),
            "evaluated_actionable": len(actionable_segment),
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()

    bars = tuple(load_csv(args.dataset))
    events = MarketMonitor().observe_history("EURUSD", "15m", bars)
    decisions = evaluate_strategy_escalation(bars, events)
    baseline = {d.index for d in decisions if d.request_ai or d.strategy_hint.request_ai}
    context = {d.index: (_tier_code(d.strategy_hint.confidence_tier), _reason_family(d.reason)) for d in decisions if d.index in baseline}

    n = len(bars)
    train_end = int(n * 0.60)
    validation_end = int(n * 0.80)

    validation = _evaluate_segment(bars, baseline, context, train_end, validation_end, history_bars=train_end)
    accepted_validation = [(threshold, result) for threshold, result in validation.items() if result["accepted"]]
    selected_threshold = max(accepted_validation, key=lambda item: item[0])[0] if accepted_validation else None

    test = _evaluate_segment(bars, baseline, context, validation_end, n, history_bars=validation_end)
    selected_test = test[selected_threshold] if selected_threshold is not None else None

    full_actionable = _actionable_indices(
        bars,
        future_bars=HORIZON,
        opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0,
        fast_period=20,
        slow_period=50,
    )
    baseline_metrics = _metrics(bars, baseline, full_actionable)

    payload = {
        "schema_version": 2,
        "dataset": args.dataset,
        "policy": "causal_candidate_risk_filter_walk_forward",
        "split": {"train_bars": train_end, "validation_bars": validation_end - train_end, "test_bars": n - validation_end},
        "recall_floor": RECALL_FLOOR,
        "baseline": baseline_metrics,
        "validation_selected_threshold": selected_threshold,
        "validation": {str(k): v for k, v in validation.items()},
        "test": {str(k): v for k, v in test.items()},
        "selected_test": selected_test,
        "deployment_status": "out_of_sample_recall_passed_candidate" if selected_test is not None and selected_test["accepted"] else "baseline_required",
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
