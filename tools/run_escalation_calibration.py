#!/usr/bin/env python3
"""Run escalation calibration across opportunity magnitudes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_research.data import load_csv
from trading_research.escalation_calibration import calibrate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    bars = load_csv(Path(args.dataset))
    points = calibrate(bars)
    payload = {
        "schema_version": 1,
        "dataset": args.dataset,
        "bars": len(bars),
        "points": [
            {
                "opportunity_move_bps": p.opportunity_move_bps,
                "recall": p.recall,
                "ai_requests": p.ai_requests,
                "missed_opportunities": p.missed_opportunities,
            }
            for p in points
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
