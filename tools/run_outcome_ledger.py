#!/usr/bin/env python3
"""Build a reusable causal historical outcome ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_research.data import load_csv
from trading_research.outcome_ledger import build_outcome_ledger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    parser.add_argument("--future-bars", type=int, default=4)
    parser.add_argument("--opportunity-move-bps", type=float, default=30.0)
    parser.add_argument("--transaction-cost-bps", type=float, default=4.0)
    parser.add_argument("--fast-period", type=int, default=20)
    parser.add_argument("--slow-period", type=int, default=50)
    args = parser.parse_args()

    bars = load_csv(args.dataset)
    records = build_outcome_ledger(
        bars,
        future_bars=args.future_bars,
        opportunity_move_bps=args.opportunity_move_bps,
        transaction_cost_bps_round_trip=args.transaction_cost_bps,
        fast_period=args.fast_period,
        slow_period=args.slow_period,
    )

    complete = [record for record in records if not record.insufficient_future_window]
    opportunities = sum(record.opportunity_label for record in complete)
    actionable = sum(record.actionable_label for record in complete)

    output = {
        "schema_version": 1,
        "policy": "causal_historical_outcome_ledger",
        "dataset": args.dataset,
        "parameters": {
            "future_bars": args.future_bars,
            "opportunity_move_bps": args.opportunity_move_bps,
            "transaction_cost_bps": args.transaction_cost_bps,
            "fast_period": args.fast_period,
            "slow_period": args.slow_period,
        },
        "summary": {
            "bars": len(bars),
            "complete_outcome_records": len(complete),
            "incomplete_future_window_records": len(records) - len(complete),
            "opportunity_labels": opportunities,
            "actionable_labels": actionable,
        },
        "causal_rule": "Decision-time feature fields contain only current/past data; future outcome fields are evaluation labels and must not be used for decisions at the same index.",
        "records": [record.to_dict() for record in records],
    }

    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: output[k] for k in ("schema_version", "policy", "dataset", "parameters", "summary", "causal_rule")}, indent=2))


if __name__ == "__main__":
    main()
