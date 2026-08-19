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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()

    bars = load_csv(args.dataset)
    if len(bars) < 50:
        report = {
            "ai_requests": 0,
            "unique_ai_request_bars": 0,
            "actionable_opportunities": 0,
            "actionable_reviewed": 0,
            "actionable_recall": 0.0,
            "opportunity_precision": 0.0,
            "unnecessary_ai_requests": 0,
        }
    else:
        from dataclasses import asdict
        from trading_research.strategy_escalation_efficiency import evaluate_strategy_escalation_efficiency
        report = asdict(evaluate_strategy_escalation_efficiency(bars))

    payload = {"schema_version": 1, "dataset": args.dataset, **report}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
