#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.data import load_csv
from trading_research.strategy_opportunity_quality import evaluate_strategy_opportunities


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: run_strategy_opportunity_quality.py DATASET [OUTPUT]")
    dataset = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "research/experiments/strategy_opportunity_quality_001.json"
    bars = load_csv(dataset)
    report = evaluate_strategy_opportunities(bars)
    payload = {"schema_version": 1, "dataset": dataset, **asdict(report)}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
