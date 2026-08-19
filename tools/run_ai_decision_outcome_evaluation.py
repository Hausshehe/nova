#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.data import load_csv
from trading_research.ai_decision_outcome_evaluation import evaluate_ai_decision_outcomes
from trading_research.market_reasoner import GroqMarketReasoner


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    parser.add_argument("--limit", type=int, default=32)
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    args = parser.parse_args()

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is required")

    bars = load_csv(args.dataset)
    reasoner = GroqMarketReasoner(api_key, model=args.model)
    report = evaluate_ai_decision_outcomes(bars, reasoner=reasoner, sample_limit=args.limit)
    payload = {"schema_version": 1, "dataset": args.dataset, "model": args.model, **asdict(report)}

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
