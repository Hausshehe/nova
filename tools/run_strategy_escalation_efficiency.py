#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.data import load_csv
from trading_research.strategy_escalation_efficiency import evaluate_strategy_escalation_efficiency


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()
    report = evaluate_strategy_escalation_efficiency(load_csv(args.dataset))
    payload = {"schema_version": 1, "dataset": args.dataset, **asdict(report)}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
