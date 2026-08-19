from __future__ import annotations

import json
import sys
from pathlib import Path

from trading_research.data import load_csv
from trading_research.directional_baseline_evaluation import evaluate_directional_baseline


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: run_directional_baseline_evaluation.py DATASET OUTPUT_JSON")
    dataset, output = sys.argv[1:]
    bars = load_csv(dataset)
    full, folds = evaluate_directional_baseline(bars)
    payload = {
        "schema_version": 1,
        "policy": "causal_trusted_candidate_sma_direction_baseline",
        "dataset": dataset,
        "parameters": {
            "future_bars": 4,
            "opportunity_move_bps": 30.0,
            "transaction_cost_bps": 4.0,
            "fast_period": 20,
            "slow_period": 50,
            "folds": 4,
        },
        "full_sample": full.to_dict(),
        "chronological_folds": [
            {"fold": fold, **metrics.to_dict()} for fold, metrics in folds
        ],
        "causal_rule": "Direction uses only the current/past SMA gap; future movement is evaluation-only.",
        "status": "report_only",
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
