#!/usr/bin/env python3
"""Compare the trusted baseline with the causal adaptive candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.data import load_csv
from trading_research.market_monitor import MarketMonitor
from trading_research.strategy_escalation import build_strategy_escalation_hints
from trading_research.strategy_escalation_bridge import evaluate_strategy_escalation
from trading_research.adaptive_opportunity_policy import build_walk_forward_policy
from trading_research.strategy_escalation_efficiency import _actionable_indices, _precision


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()

    bars = tuple(load_csv(args.dataset))
    monitor = MarketMonitor()
    events = monitor.observe_history("EURUSD", "15m", bars)
    decisions = evaluate_strategy_escalation(bars, events)

    baseline = {
        decision.index
        for decision in decisions
        if decision.request_ai or decision.strategy_hint.request_ai
    }
    adaptive = build_walk_forward_policy(bars, candidate_indices=baseline)
    adaptive_indices = {decision.index for decision in adaptive if decision.request_ai}

    actionable = _actionable_indices(
        bars,
        future_bars=4,
        opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0,
        fast_period=20,
        slow_period=50,
    )

    def metrics(indices: set[int]) -> dict[str, float | int]:
        reviewed = len(actionable & indices)
        precision, justified = _precision(
            bars,
            indices,
            future_bars=4,
            opportunity_move_bps=30.0,
        )
        return {
            "ai_requests": len(indices),
            "unique_ai_request_bars": len(indices),
            "actionable_opportunities": len(actionable),
            "actionable_reviewed": reviewed,
            "actionable_recall": reviewed / len(actionable) if actionable else 0.0,
            "opportunity_precision": precision,
            "unnecessary_ai_requests": max(0, len(indices) - justified),
        }

    baseline_metrics = metrics(baseline)
    adaptive_metrics = metrics(adaptive_indices)
    recall_floor = 0.98
    accepted = adaptive_metrics["actionable_recall"] >= recall_floor
    selected = adaptive_indices if accepted else baseline

    payload = {
        "schema_version": 1,
        "dataset": args.dataset,
        "policy": "adaptive_filter_over_trusted_baseline",
        "recall_floor": recall_floor,
        "adaptive_accepted": accepted,
        "baseline": baseline_metrics,
        "adaptive_candidate": adaptive_metrics,
        "selected": metrics(selected),
        "delta": {
            "ai_requests": adaptive_metrics["ai_requests"] - baseline_metrics["ai_requests"],
            "actionable_recall": adaptive_metrics["actionable_recall"] - baseline_metrics["actionable_recall"],
            "opportunity_precision": adaptive_metrics["opportunity_precision"] - baseline_metrics["opportunity_precision"],
            "unnecessary_ai_requests": adaptive_metrics["unnecessary_ai_requests"] - baseline_metrics["unnecessary_ai_requests"],
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
