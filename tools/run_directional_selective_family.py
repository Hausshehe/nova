from __future__ import annotations

import json
import sys
from pathlib import Path

from trading_research.data import load_csv
from trading_research.directional_selective_family import evaluate_directional_selective_family


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: run_directional_selective_family.py DATASET OUTPUT_JSON")

    dataset = Path(sys.argv[1])
    output = Path(sys.argv[2])
    bars = load_csv(dataset)
    metrics = evaluate_directional_selective_family(bars)
    payload = {
        "schema_version": 1,
        "policy": "predefined_causal_directional_selectivity_family",
        "dataset": str(dataset),
        "selection_rule": "Policies are fixed before evaluation; future labels are never used to select a policy.",
        "parameters": {
            "future_bars": 4,
            "transaction_cost_bps": 4.0,
            "fast_period": 20,
            "slow_period": 50,
            "folds": 4,
        },
        "policies": [item.to_dict() for item in metrics],
        "causal_rule": "Direction and SMA-gap filters use current/past closes only; future close movement is evaluation-only.",
        "status": "report_only",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
