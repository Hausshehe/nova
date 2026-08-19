#!/usr/bin/env python3
"""Causal candidate-risk filtering over the trusted AI-review baseline."""

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


def _features(bars, index: int, *, fast_period: int = 20, slow_period: int = 50, momentum_lookback: int = 3):
    if index + 1 < slow_period:
        return 0.0, 0.0, 0.0
    fast = sum(x.close for x in bars[index-fast_period+1:index+1]) / fast_period
    slow = sum(x.close for x in bars[index-slow_period+1:index+1]) / slow_period
    gap = abs(fast / slow - 1.0) * 10_000.0 if slow else 0.0
    start = max(0, index - momentum_lookback)
    momentum = abs(bars[index].close / bars[start].close - 1.0) * 10_000.0 if bars[start].close else 0.0
    slope = 0.0
    if index >= momentum_lookback and start + 1 >= slow_period:
        start_fast = sum(x.close for x in bars[start-fast_period+1:start+1]) / fast_period
        start_slow = sum(x.close for x in bars[start-slow_period+1:start+1]) / slow_period
        start_gap = abs(start_fast / start_slow - 1.0) * 10_000.0 if start_slow else 0.0
        slope = gap - start_gap
    return momentum, gap, slope


def _bucket(bars, index: int, context: dict[int, tuple[int, int]], *, width: float) -> tuple[int, int, int, int, int]:
    momentum, gap, slope = _features(bars, index)
    tier, reason = context.get(index, (-1, -1))
    return (int(momentum // width), int(gap // width), int(abs(slope) // width), tier, reason)


def _metrics(bars, indices: set[int], actionable: set[int], *, opportunity_move_bps: float = 30.0):
    reviewed = len(indices & actionable)
    precision, justified = _precision(bars, indices, future_bars=4, opportunity_move_bps=opportunity_move_bps)
    return {
        "ai_requests": len(indices),
        "actionable_opportunities": len(actionable),
        "actionable_reviewed": reviewed,
        "actionable_recall": reviewed / len(actionable) if actionable else 0.0,
        "opportunity_precision": precision,
        "not_actionable_requests": len(indices - actionable),
        "unnecessary_ai_requests_legacy_precision_definition": max(0, len(indices) - justified),
    }


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

    actionable = _actionable_indices(
        bars,
        future_bars=4,
        opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0,
        fast_period=20,
        slow_period=50,
    )

    history: dict[tuple[int, int, int, int, int], deque[bool]] = defaultdict(lambda: deque(maxlen=500))
    decisions_by_threshold: dict[float, set[int]] = {}
    # Wider sweep: the first experiment showed that 0.15..0.40 all selected
    # the same policy. Continue upward to discover the actual recall boundary
    # instead of assuming the adaptive idea has no useful headroom.
    thresholds = (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
    min_samples = 20
    width = 25.0

    for index in range(len(bars)):
        label_index = index - 4
        if label_index >= 0 and label_index in baseline:
            label = label_index in actionable
            history[_bucket(bars, label_index, context, width=width)].append(label)

        probabilities: list[float] = []
        bucket = _bucket(bars, index, context, width=width)
        prior = history[bucket]
        if len(prior) >= min_samples:
            probabilities.append(sum(prior) / len(prior))
        ctx = context.get(index)
        if ctx is not None:
            broader = [value for key, values in history.items() if key[3:] == ctx for value in values]
            if len(broader) >= min_samples:
                probabilities.append(sum(broader) / len(broader))
            tier_values = [value for key, values in history.items() if key[3] == ctx[0] for value in values]
            if len(tier_values) >= min_samples:
                probabilities.append(sum(tier_values) / len(tier_values))

        p_actionable = min(probabilities) if probabilities else None
        for threshold in thresholds:
            selected = decisions_by_threshold.setdefault(threshold, set())
            if index in baseline and not (p_actionable is not None and p_actionable < threshold):
                selected.add(index)

    baseline_metrics = _metrics(bars, baseline, actionable)
    candidates: dict[str, dict[str, object]] = {}
    for threshold, selected_indices in decisions_by_threshold.items():
        recall = len(selected_indices & actionable) / len(actionable) if actionable else 0.0
        accepted = recall >= 0.98
        effective = selected_indices if accepted else baseline
        candidates[str(threshold)] = {
            "accepted": accepted,
            "suppressed": len(baseline - selected_indices),
            "metrics": _metrics(bars, effective, actionable),
        }

    accepted_policies = [(float(t), result) for t, result in candidates.items() if result["accepted"]]
    if accepted_policies:
        selected_threshold, selected_result = min(accepted_policies, key=lambda item: item[1]["metrics"]["ai_requests"])
        selected = selected_result["metrics"]
    else:
        selected_threshold = None
        selected = baseline_metrics

    payload = {
        "schema_version": 2,
        "dataset": args.dataset,
        "policy": "causal_candidate_risk_filter",
        "recall_floor": 0.98,
        "baseline": baseline_metrics,
        "candidate_policies": candidates,
        "selected_threshold": selected_threshold,
        "selected": selected,
        "accounting_note": "not_actionable_requests counts baseline bars outside the actionable-opportunity set; the legacy precision metric counts requests without a >=30 bps future move. These are intentionally separate metrics.",
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
