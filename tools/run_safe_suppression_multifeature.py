#!/usr/bin/env python3
"""Causal multifeature safe-suppression experiment over trusted AI-review candidates."""

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

HORIZON = 4
FLOOR = 0.98
MIN_SAMPLES = 20
THRESHOLDS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30)


def tier_code(t: str) -> int:
    return {"WEAK": 0, "DEVELOPING": 1, "STRONG": 2}.get(t, -1)


def reason_family(r: str) -> int:
    if r.startswith("strong strategy hint"):
        return 1
    if r.startswith("developing strategy"):
        return 2
    if r.startswith("new bar"):
        return 3
    if "price move" in r:
        return 4
    return 0


def features(bars, i: int) -> tuple[int, int, int, int, int, int]:
    fast, slow, lookback = 20, 50, 3
    if i + 1 < slow:
        return (0, 0, 0, 0, 0, 0)
    f = sum(x.close for x in bars[i-fast+1:i+1]) / fast
    s = sum(x.close for x in bars[i-slow+1:i+1]) / slow
    gap = abs(f / s - 1.0) * 10_000 if s else 0.0
    start = max(0, i - lookback)
    momentum = abs(bars[i].close / bars[start].close - 1.0) * 10_000 if bars[start].close else 0.0
    slope = 0.0
    if i >= lookback and start + 1 >= slow:
        sf = sum(x.close for x in bars[start-fast+1:start+1]) / fast
        ss = sum(x.close for x in bars[start-slow+1:start+1]) / slow
        sg = abs(sf / ss - 1.0) * 10_000 if ss else 0.0
        slope = gap - sg
    return (
        int(momentum // 10.0),
        int(gap // 10.0),
        int(abs(slope) // 10.0),
        int(abs(slope) >= 3.0),
        int(momentum >= 5.0),
        int(gap >= 50.0),
    )


def context_key(decision):
    return (tier_code(decision.strategy_hint.confidence_tier), reason_family(decision.reason))


def metrics(bars, idxs, actionable):
    reviewed = len(idxs & actionable)
    precision, justified = _precision(bars, idxs, future_bars=HORIZON, opportunity_move_bps=30.0)
    return {
        "ai_requests": len(idxs),
        "actionable_reviewed": reviewed,
        "actionable_recall": reviewed / len(actionable) if actionable else 0.0,
        "opportunity_precision": precision,
        "not_actionable_requests": len(idxs - actionable),
        "legacy_unnecessary_requests": max(0, len(idxs) - justified),
    }


def evaluate_segment(bars, baseline, decisions, start, end, history_end):
    history = defaultdict(lambda: deque(maxlen=500))
    actionable_full = _actionable_indices(
        bars[:history_end], future_bars=HORIZON, opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0, fast_period=20, slow_period=50,
    )
    # Only labels whose full horizon is before the history boundary are used.
    for i in range(HORIZON, history_end):
        j = i - HORIZON
        if j not in baseline:
            continue
        d = decisions[j]
        key = (features(bars, j), context_key(d))
        history[key].append(j in actionable_full)

    actionable = _actionable_indices(
        bars[start:end], future_bars=HORIZON, opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0, fast_period=20, slow_period=50,
    )
    actionable = {i + start for i in actionable}
    base_slice = {i for i in baseline if start <= i < end}
    out = {}
    for threshold in THRESHOLDS:
        selected = set(base_slice)
        suppressed = set()
        for i in sorted(base_slice):
            d = decisions[i]
            key = (features(bars, i), context_key(d))
            prior = history[key]
            if len(prior) < MIN_SAMPLES:
                continue
            p_actionable = sum(prior) / len(prior)
            # Suppress only when the historical actionable probability is low.
            if p_actionable <= threshold:
                selected.discard(i)
                suppressed.add(i)
        m = metrics(bars, selected, actionable)
        out[str(threshold)] = {
            "metrics": m,
            "suppressed": len(suppressed),
            "accepted": m["actionable_recall"] >= FLOOR,
        }
    base_m = metrics(bars, base_slice, actionable)
    return {"baseline": base_m, "thresholds": out, "evaluated_bars": end-start, "evaluated_actionable": len(actionable)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("output")
    args = ap.parse_args()

    bars = tuple(load_csv(args.dataset))
    events = MarketMonitor().observe_history("EURUSD", "15m", bars)
    decisions = evaluate_strategy_escalation(bars, events)
    baseline = {d.index for d in decisions if d.request_ai or d.strategy_hint.request_ai}

    n = len(bars)
    # Four rolling causal folds with 50% train, 10% validation, 10% test-style windows.
    folds = []
    starts = (0, int(n*0.10), int(n*0.20), int(n*0.30))
    for fold_no, offset in enumerate(starts, 1):
        train_end = min(n, int(n*0.50) + offset)
        validation_end = min(n, train_end + int(n*0.10))
        test_end = min(n, validation_end + int(n*0.10))
        validation = evaluate_segment(bars, baseline, decisions, train_end, validation_end, train_end)
        valid = [(float(t), r) for t, r in validation["thresholds"].items() if r["accepted"]]
        selected_threshold = max(valid, key=lambda x: x[0])[0] if valid else None
        test = evaluate_segment(bars, baseline, decisions, validation_end, test_end, validation_end)
        selected_test = test["thresholds"].get(str(selected_threshold)) if selected_threshold is not None else None
        folds.append({
            "fold": fold_no,
            "train": [offset, train_end],
            "validation": validation,
            "selected_threshold": selected_threshold,
            "test": test,
            "selected_test": selected_test,
        })

    full_actionable = _actionable_indices(
        bars, future_bars=HORIZON, opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0, fast_period=20, slow_period=50,
    )
    payload = {
        "schema_version": 1,
        "dataset": args.dataset,
        "policy": "causal_multifeature_safe_suppression",
        "recall_floor": FLOOR,
        "baseline_full": metrics(bars, baseline, full_actionable),
        "folds": folds,
        "deployment_status": "diagnostic_only",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
