#!/usr/bin/env python3
"""Run the escalation opportunity-recall diagnostic on historical OHLCV data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from trading_research.data import load_csv
from trading_research.opportunity_recall import evaluate_opportunity_recall


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("--output", required=True)
    parser.add_argument("--future-bars", type=int, default=4)
    parser.add_argument("--opportunity-move-bps", type=float, default=30.0)
    args = parser.parse_args()

    bars = load_csv(args.dataset)
    report = evaluate_opportunity_recall(
        bars,
        future_bars=args.future_bars,
        opportunity_move_bps=args.opportunity_move_bps,
    )
    payload = {
        "schema_version": 1,
        "dataset": args.dataset,
        "bars": len(bars),
        "future_bars": args.future_bars,
        "opportunity_move_bps": args.opportunity_move_bps,
        "opportunities": report.opportunities,
        "opportunities_with_ai_review": report.opportunities_with_ai_review,
        "missed_opportunities": report.missed_opportunities,
        "recall": report.recall,
        "ai_requests": report.ai_requests,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
