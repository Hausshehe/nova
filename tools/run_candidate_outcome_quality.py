#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from trading_research.candidate_outcome_quality import evaluate_candidate_outcome_quality
from trading_research.data import load_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    parser.add_argument("--future-bars", type=int, default=4)
    parser.add_argument("--opportunity-move-bps", type=float, default=30.0)
    parser.add_argument("--transaction-cost-bps", type=float, default=4.0)
    parser.add_argument("--fast-period", type=int, default=20)
    parser.add_argument("--slow-period", type=int, default=50)
    parser.add_argument("--folds", type=int, default=4)
    args = parser.parse_args()

    bars = load_csv(args.dataset)
    full, folds = evaluate_candidate_outcome_quality(
        bars,
        future_bars=args.future_bars,
        opportunity_move_bps=args.opportunity_move_bps,
        transaction_cost_bps=args.transaction_cost_bps,
        fast_period=args.fast_period,
        slow_period=args.slow_period,
        folds=args.folds,
    )
    payload = {
        "schema_version": 1,
        "policy": "trusted_high_recall_candidate_outcome_quality",
        "dataset": args.dataset,
        "parameters": {
            "future_bars": args.future_bars,
            "opportunity_move_bps": args.opportunity_move_bps,
            "transaction_cost_bps": args.transaction_cost_bps,
            "fast_period": args.fast_period,
            "slow_period": args.slow_period,
            "folds": args.folds,
        },
        "full_sample": asdict(full),
        "chronological_folds": [
            {"fold": fold, **asdict(metrics)} for fold, metrics in folds
        ],
        "research_rule": "Outcome fields are evaluation-only labels. This report measures opportunity quality and movement, not realized profit or loss, because the candidate layer does not encode a trade direction or position-management rule.",
        "status": "report_only",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
