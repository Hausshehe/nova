#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.data import load_csv
from trading_research.high_recall_candidate_policy import high_recall_candidate_indices
from trading_research.strategy_escalation_efficiency import _actionable_indices


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    parser.add_argument("--recall-floor", type=float, default=0.98)
    args = parser.parse_args()

    bars = load_csv(args.dataset)
    candidates = high_recall_candidate_indices(bars)
    actionable = _actionable_indices(
        bars,
        future_bars=4,
        opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0,
        fast_period=20,
        slow_period=50,
    )
    reviewed = actionable & candidates
    recall = len(reviewed) / len(actionable) if actionable else 0.0

    payload = {
        "schema_version": 1,
        "policy": "high_recall_union_candidate",
        "dataset": args.dataset,
        "recall_floor": args.recall_floor,
        "bars": len(bars),
        "candidate_ai_requests": len(candidates),
        "unique_candidate_bars": len(candidates),
        "actionable_opportunities": len(actionable),
        "actionable_reviewed": len(reviewed),
        "actionable_recall": recall,
        "recall_floor_pass": recall >= args.recall_floor,
        "safe_to_advance": recall >= args.recall_floor,
        "causal_rule": "Candidate evidence uses current/past market and strategy state only; future movement is evaluation-only.",
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
