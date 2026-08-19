#!/usr/bin/env python3
"""Diagnose causal candidate-risk separability across chronological folds."""

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
from trading_research.strategy_escalation_efficiency import _actionable_indices

HORIZON = 4
WIDTH = 25.0
MIN_SAMPLES = 20
THRESHOLDS = (0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


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
    if index + 1 < 50:
        return 0.0, 0.0, 0.0
    fast = sum(x.close for x in bars[index - 19 : index + 1]) / 20
    slow = sum(x.close for x in bars[index - 49 : index + 1]) / 50
    gap = abs(fast / slow - 1.0) * 10_000.0 if slow else 0.0
    start = max(0, index - 3)
    momentum = abs(bars[index].close / bars[start].close - 1.0) * 10_000.0 if bars[start].close else 0.0
    slope = 0.0
    if index >= 3 and start + 1 >= 50:
        start_fast = sum(x.close for x in bars[start - 19 : start + 1]) / 20
        start_slow = sum(x.close for x in bars[start - 49 : start + 1]) / 50
        start_gap = abs(start_fast / start_slow - 1.0) * 10_000.0 if start_slow else 0.0
        slope = gap - start_gap
    return momentum, gap, slope


def _bucket(bars, index: int, context):
    momentum, gap, slope = _features(bars, index)
    tier, reason = context.get(index, (-1, -1))
    return (
        int(momentum // WIDTH),
        int(gap // WIDTH),
        int(abs(slope) // WIDTH),
        tier,
        reason,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()

    bars = tuple(load_csv(args.dataset))
    events = MarketMonitor().observe_history("EURUSD", "15m", bars)
    decisions = evaluate_strategy_escalation(bars, events)
    baseline = {d.index for d in decisions if d.request_ai or d.strategy_hint.request_ai}
    context = {
        d.index: (_tier_code(d.strategy_hint.confidence_tier), _reason_family(d.reason))
        for d in decisions if d.index in baseline
    }

    n = len(bars)
    fold_size = n // 5
    folds = []
    all_risk_scores: list[float] = []

    for fold in range(4):
        train_end = fold_size * (fold + 1)
        test_end = min(n, train_end + fold_size)
        history: dict[tuple[int, int, int, int, int], deque[bool]] = defaultdict(lambda: deque(maxlen=500))
        train_actionable = _actionable_indices(
            bars[:train_end],
            future_bars=HORIZON,
            opportunity_move_bps=30.0,
            transaction_cost_bps_round_trip=4.0,
            fast_period=20,
            slow_period=50,
        )

        for index in range(HORIZON, train_end):
            label_index = index - HORIZON
            if label_index not in baseline:
                continue
            label = label_index in train_actionable
            history[_bucket(bars, label_index, context)].append(label)

        test_actionable_local = _actionable_indices(
            bars[train_end:test_end],
            future_bars=HORIZON,
            opportunity_move_bps=30.0,
            transaction_cost_bps_round_trip=4.0,
            fast_period=20,
            slow_period=50,
        )
        test_actionable = {i + train_end for i in test_actionable_local}
        test_candidates = baseline & set(range(train_end, test_end))

        rows = []
        for index in sorted(test_candidates):
            probabilities: list[float] = []
            bucket = _bucket(bars, index, context)
            exact = history[bucket]
            if len(exact) >= MIN_SAMPLES:
                probabilities.append(sum(exact) / len(exact))
            ctx = context.get(index)
            if ctx is not None:
                broader_values = [v for key, values in history.items() if key[3:] == ctx for v in values]
                tier_values = [v for key, values in history.items() if key[3] == ctx[0] for v in values]
                if len(broader_values) >= MIN_SAMPLES:
                    probabilities.append(sum(broader_values) / len(broader_values))
                if len(tier_values) >= MIN_SAMPLES:
                    probabilities.append(sum(tier_values) / len(tier_values))

            score = min(probabilities) if probabilities else None
            if score is not None:
                all_risk_scores.append(score)
            rows.append({
                "index": index,
                "score": score,
                "actionable": index in test_actionable,
                "context": context.get(index),
            })

        fold_result = {
            "fold": fold + 1,
            "train": [0, train_end],
            "test": [train_end, test_end],
            "candidates": len(rows),
            "actionable": len([r for r in rows if r["actionable"]]),
            "scored": len([r for r in rows if r["score"] is not None]),
            "unscored": len([r for r in rows if r["score"] is None]),
            "score_bins": {},
            "thresholds": {},
        }

        bins = defaultdict(lambda: {"candidates": 0, "actionable": 0})
        for row in rows:
            if row["score"] is None:
                continue
            key = min(0.95, int(row["score"] * 20) / 20)
            bins[f"{key:.2f}"]["candidates"] += 1
            bins[f"{key:.2f}"]["actionable"] += int(row["actionable"])
        for key, value in sorted(bins.items()):
            total = value["candidates"]
            value["actionable_rate"] = value["actionable"] / total if total else 0.0
        fold_result["score_bins"] = dict(bins)

        for threshold in THRESHOLDS:
            selected = {r["index"] for r in rows if r["score"] is None or r["score"] >= threshold}
            recalled = len(selected & test_actionable)
            recall = recalled / len(test_actionable) if test_actionable else 0.0
            fold_result["thresholds"][str(threshold)] = {
                "ai_requests": len(selected),
                "suppressed": len(test_candidates - selected),
                "recall": recall,
                "accepted": recall >= 0.98,
            }

        folds.append(fold_result)

    payload = {
        "schema_version": 1,
        "dataset": args.dataset,
        "policy": "candidate_risk_separability_diagnostics",
        "purpose": "diagnose whether causal risk scores can separate safe-to-suppress candidates from actionable candidates",
        "thresholds": THRESHOLDS,
        "folds": folds,
        "global_score_summary": {
            "scored_candidates": len(all_risk_scores),
            "min": min(all_risk_scores) if all_risk_scores else None,
            "max": max(all_risk_scores) if all_risk_scores else None,
            "mean": sum(all_risk_scores) / len(all_risk_scores) if all_risk_scores else None,
        },
        "deployment_status": "diagnostic_only",
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
