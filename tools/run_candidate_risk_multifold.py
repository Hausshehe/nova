#!/usr/bin/env python3
"""Multi-fold causal validation for conservative candidate-risk filtering."""

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
HORIZON = 4
MIN_SAMPLES = 20
WIDTH = 25.0
N_FOLDS = 4
TRAIN_RATIO = 0.50
VAL_RATIO = 0.10
TEST_RATIO = 0.10


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
    fast_period, slow_period, lookback = 20, 50, 3
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


def _bucket(bars, index: int, context, *, width: float = WIDTH):
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


def _build_history(bars, baseline, context, history_end):
    history = defaultdict(lambda: deque(maxlen=500))
    actionable_history = _actionable_indices(
        bars[:history_end], future_bars=HORIZON, opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0, fast_period=20, slow_period=50,
    )
    for index in range(HORIZON, history_end):
        label_index = index - HORIZON
        if label_index not in baseline:
            continue
        history[_bucket(bars, label_index, context)].append(label_index in actionable_history)
    return history


def _score(index, bars, baseline, context, history):
    if index not in baseline:
        return None
    probabilities = []
    bucket = _bucket(bars, index, context)
    prior = history[bucket]
    if len(prior) >= MIN_SAMPLES:
        probabilities.append(sum(prior) / len(prior))
    ctx = context.get(index)
    if ctx is not None:
        broader = [v for key, vals in history.items() if key[3:] == ctx for v in vals]
        tier_values = [v for key, vals in history.items() if key[3] == ctx[0] for v in vals]
        if len(broader) >= MIN_SAMPLES:
            probabilities.append(sum(broader) / len(broader))
        if len(tier_values) >= MIN_SAMPLES:
            probabilities.append(sum(tier_values) / len(tier_values))
    return min(probabilities) if probabilities else None


def _evaluate_window(bars, baseline, context, start, end, history_end, threshold):
    history = _build_history(bars, baseline, context, history_end)
    selected = {i for i in range(start, end) if (p := _score(i, bars, baseline, context, history)) is None or p >= threshold}
    selected &= baseline
    actionable = _actionable_indices(
        bars, future_bars=HORIZON, opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0, fast_period=20, slow_period=50,
    )
    window_actionable = {i for i in actionable if start <= i < end}
    metrics = _metrics(bars, selected, window_actionable)
    metrics["evaluated_bars"] = end - start
    metrics["evaluated_actionable"] = len(window_actionable)
    metrics["accepted"] = metrics["actionable_recall"] >= RECALL_FLOOR
    metrics["suppressed"] = len((baseline & set(range(start, end))) - selected)
    return metrics


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
    full_actionable = _actionable_indices(
        bars, future_bars=HORIZON, opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0, fast_period=20, slow_period=50,
    )

    n = len(bars)
    window = max(1, int(n * TEST_RATIO))
    train_len = int(n * TRAIN_RATIO)
    val_len = int(n * VAL_RATIO)
    folds = []
    for fold in range(N_FOLDS):
        train_end = train_len + fold * window
        val_start = train_end
        val_end = val_start + val_len
        test_start = val_end
        test_end = test_start + window
        if test_end > n:
            break

        validation = {str(t): _evaluate_window(bars, baseline, context, val_start, val_end, train_end, t) for t in THRESHOLDS}
        eligible = [(float(t), r) for t, r in validation.items() if r["accepted"]]
        # Do not select an adaptive threshold on a fold whose baseline itself fails the safety floor.
        val_baseline = _metrics(bars, baseline & set(range(val_start, val_end)), {i for i in full_actionable if val_start <= i < val_end})
        baseline_eligible = val_baseline["actionable_recall"] >= RECALL_FLOOR
        selected_threshold = max(eligible, key=lambda item: item[0])[0] if eligible and baseline_eligible else None
        test = {str(t): _evaluate_window(bars, baseline, context, test_start, test_end, val_end, t) for t in THRESHOLDS}
        selected_test = test[str(selected_threshold)] if selected_threshold is not None else None
        folds.append({
            "fold": fold + 1,
            "train": [0, train_end],
            "validation": [val_start, val_end],
            "test": [test_start, test_end],
            "validation_baseline": val_baseline,
            "validation_baseline_meets_floor": baseline_eligible,
            "validation_selected_threshold": selected_threshold,
            "validation": validation,
            "test": test,
            "selected_test": selected_test,
            "status": "adaptive_candidate_tested" if selected_test is not None else "baseline_or_no_valid_threshold",
        })

    testable = [f for f in folds if f["selected_test"] is not None]
    adaptive_passes = [f for f in testable if f["selected_test"]["accepted"]]
    aggregate_suppressed = sum(f["selected_test"]["suppressed"] for f in adaptive_passes)
    aggregate_requests = sum(f["selected_test"]["ai_requests"] for f in adaptive_passes)
    aggregate_actionable = sum(f["selected_test"]["evaluated_actionable"] for f in adaptive_passes)
    aggregate_reviewed = sum(f["selected_test"]["actionable_reviewed"] for f in adaptive_passes)
    aggregate_recall = aggregate_reviewed / aggregate_actionable if aggregate_actionable else None

    payload = {
        "schema_version": 1,
        "dataset": args.dataset,
        "policy": "causal_candidate_risk_filter_multifold",
        "fold_design": {"folds_requested": N_FOLDS, "train_ratio": TRAIN_RATIO, "validation_ratio": VAL_RATIO, "test_ratio": TEST_RATIO},
        "recall_floor": RECALL_FLOOR,
        "baseline_full": _metrics(bars, baseline, full_actionable),
        "folds": folds,
        "aggregate_testable_adaptive": {
            "testable_folds": len(testable),
            "passing_folds": len(adaptive_passes),
            "suppressed_requests_sum": aggregate_suppressed,
            "ai_requests_sum": aggregate_requests,
            "actionable_sum": aggregate_actionable,
            "reviewed_sum": aggregate_reviewed,
            "aggregate_recall": aggregate_recall,
        },
        "deployment_status": "candidate_requires_more_evidence" if not testable or len(adaptive_passes) < len(testable) else "adaptive_candidate_passed_all_testable_folds",
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
