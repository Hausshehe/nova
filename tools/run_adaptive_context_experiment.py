#!/usr/bin/env python3
"""Run the adaptive filter with observable strategy/escalation context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.adaptive_opportunity_policy import build_walk_forward_policy
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


def _metrics(bars, indices: set[int], actionable: set[int]) -> dict[str, float | int]:
    reviewed = len(indices & actionable)
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()

    bars = tuple(load_csv(args.dataset))
    events = MarketMonitor().observe_history("EURUSD", "15m", bars)
    decisions = evaluate_strategy_escalation(bars, events)
    baseline = {
        d.index for d in decisions if d.request_ai or d.strategy_hint.request_ai
    }

    # These are observable at decision time. They do not contain outcome labels.
    context = {
        d.index: (_tier_code(d.strategy_hint.confidence_tier), _reason_family(d.reason))
        for d in decisions
        if d.index in baseline
    }

    adaptive = build_walk_forward_policy(
        bars,
        candidate_indices=baseline,
        observable_context=context,
    )
    adaptive_indices = {d.index for d in adaptive if d.request_ai}

    actionable = _actionable_indices(
        bars,
        future_bars=4,
        opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0,
        fast_period=20,
        slow_period=50,
    )

    baseline_metrics = _metrics(bars, baseline, actionable)
    adaptive_metrics = _metrics(bars, adaptive_indices, actionable)
    recall_floor = 0.98
    accepted = adaptive_metrics["actionable_recall"] >= recall_floor
    selected = adaptive_indices if accepted else baseline

    suppression_reasons: dict[str, int] = {}
    evidence_reasons: dict[str, int] = {}
    for d in adaptive:
        if d.index not in baseline:
            continue
        target = suppression_reasons if "suppression" in d.reason else evidence_reasons
        target[d.reason] = target.get(d.reason, 0) + 1

    payload = {
        "schema_version": 1,
        "dataset": args.dataset,
        "policy": "adaptive_filter_over_trusted_baseline",
        "adaptive_context": "strategy_confidence_tier_plus_coarse_escalation_reason",
        "recall_floor": recall_floor,
        "adaptive_accepted": accepted,
        "baseline": baseline_metrics,
        "adaptive_candidate": adaptive_metrics,
        "selected": _metrics(bars, selected, actionable),
        "delta": {
            "ai_requests": adaptive_metrics["ai_requests"] - baseline_metrics["ai_requests"],
            "actionable_recall": adaptive_metrics["actionable_recall"] - baseline_metrics["actionable_recall"],
            "opportunity_precision": adaptive_metrics["opportunity_precision"] - baseline_metrics["opportunity_precision"],
            "unnecessary_ai_requests": adaptive_metrics["unnecessary_ai_requests"] - baseline_metrics["unnecessary_ai_requests"],
        },
        "diagnostics": {
            "baseline_candidates": len(baseline),
            "suppressed_candidates": len(baseline - adaptive_indices),
            "suppression_reasons": suppression_reasons,
            "evidence_reasons": evidence_reasons,
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
