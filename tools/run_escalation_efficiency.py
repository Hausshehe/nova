#!/usr/bin/env python3
"""Run escalation efficiency diagnostics on historical data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_research.data import load_csv
from trading_research.escalation_efficiency import evaluate_efficiency


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("--output", required=True)
    parser.add_argument("--opportunity-bps", type=float, default=30.0)
    parser.add_argument("--future-bars", type=int, default=4)
    args = parser.parse_args()

    bars = load_csv(Path(args.dataset))
    report = evaluate_efficiency(
        bars,
        opportunity_move_bps=args.opportunity_bps,
        future_bars=args.future_bars,
    )
    payload = {
        "schema_version": 1,
        "dataset": args.dataset,
        "bars": len(bars),
        "opportunity_move_bps": args.opportunity_bps,
        "future_bars": args.future_bars,
        "ai_requests": report.ai_requests,
        "justified_ai_requests": report.justified_ai_requests,
        "unnecessary_ai_requests": report.unnecessary_ai_requests,
        "precision": report.precision,
        "future_opportunities": report.future_opportunities,
        "recalled_opportunities": report.recalled_opportunities,
        "recall": report.recall,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
