#!/usr/bin/env python3
"""Evaluate the existing strategy-escalation policy against causal outcomes.

This is a diagnostic gate only. It does not change policy behavior, optimize
thresholds, or use future outcomes as decision-time inputs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

from trading_research.data import load_csv
from trading_research.market_monitor import MarketMonitor
from trading_research.strategy_escalation_bridge import evaluate_strategy_escalation


def _outcome_for_index(bars, index: int, *, future_bars: int = 4, move_bps: float = 30.0, cost_bps: float = 4.0):
    if index + future_bars >= len(bars):
        return None
    base = bars[index].close
    future = bars[index + 1 : index + 1 + future_bars]
    moves = [(b.close / base - 1.0) * 10_000 for b in future]
    max_up = max(moves)
    max_down = min(moves)
    max_abs = max(abs(x) for x in moves)
    opportunity = max_abs >= move_bps
    actionable = opportunity and max_abs >= move_bps + cost_bps
    return {"max_up_bps": max_up, "max_down_bps": max_down, "max_abs_bps": max_abs, "opportunity": opportunity, "actionable": actionable}


def _evaluate_segment(bars, start: int, end: int):
    monitor = MarketMonitor()
    events = monitor.observe_history("EURUSD", "D1", bars)
    decisions = evaluate_strategy_escalation(bars, events)
    by_index = {d.index: d for d in decisions if start <= d.index < end}
    rows = []
    for index in range(start, end):
        outcome = _outcome_for_index(bars, index)
        if outcome is None or index not in by_index:
            continue
        decision = by_index[index]
        rows.append((decision, outcome))

    actionable = [o for _, o in rows if o["actionable"]]
    reviewed_actionable = [o for d, o in rows if d.request_ai and o["actionable"]]
    reviewed = [o for d, o in rows if d.request_ai]
    unnecessary = [o for d, o in rows if d.request_ai and not o["actionable"]]
    recall = len(reviewed_actionable) / len(actionable) if actionable else 0.0
    precision = len(reviewed_actionable) / len(reviewed) if reviewed else 0.0
    return {
        "evaluated_bars": len(rows),
        "ai_requests": len(reviewed),
        "actionable_opportunities": len(actionable),
        "actionable_reviewed": len(reviewed_actionable),
        "actionable_recall": recall,
        "opportunity_precision": precision,
        "unnecessary_ai_requests": len(unnecessary),
        "mean_max_abs_bps_reviewed": mean(o["max_abs_bps"] for o in reviewed) if reviewed else 0.0,
        "mean_max_abs_bps_actionable_reviewed": mean(o["max_abs_bps"] for o in reviewed_actionable) if reviewed_actionable else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()

    bars = load_csv(args.dataset)
    n = len(bars)
    fold_size = n // 4
    folds = []
    for fold in range(4):
        start = fold * fold_size
        end = n if fold == 3 else (fold + 1) * fold_size
        metrics = _evaluate_segment(bars, start, end)
        metrics["recall_floor_pass"] = metrics["actionable_recall"] >= 0.98
        folds.append({"fold": fold + 1, "range": [start, end], **metrics})

    full = _evaluate_segment(bars, 0, n)
    passing_folds = sum(1 for f in folds if f["recall_floor_pass"])
    if full["actionable_recall"] < 0.98 or passing_folds < 3:
        status = "REJECT"
        reason = "existing policy does not meet the causal decision-quality recall gate robustly across chronological folds"
    else:
        status = "PROMISING"
        reason = "existing policy meets the causal recall gate on the full sample and at least three chronological folds"

    result = {
        "schema_version": 1,
        "policy": "existing_strategy_escalation_decision_quality",
        "dataset": args.dataset,
        "parameters": {"future_bars": 4, "opportunity_move_bps": 30.0, "transaction_cost_bps": 4.0, "folds": 4},
        "full_sample": full,
        "chronological_folds": folds,
        "gate": {"recall_floor": 0.98, "required_passing_folds": 3, "passing_folds": passing_folds, "status": status, "reason": reason},
        "causal_rule": "Only decision-time strategy/escalation state is used to form the policy decision; future movement is evaluation-only label data.",
    }
    text = json.dumps(result, indent=2)
    print(text)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
