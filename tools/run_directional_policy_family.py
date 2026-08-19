from __future__ import annotations

import json
import sys
from pathlib import Path

from trading_research.data import load_csv
from trading_research.directional_policy_family import evaluate_directional_policy_family


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: run_directional_policy_family.py DATASET OUTPUT")
    dataset, output = sys.argv[1:]
    bars = load_csv(dataset)
    metrics = evaluate_directional_policy_family(bars)
    report = {
        "schema_version": 1,
        "policy": "predefined_causal_directional_policy_family",
        "dataset": dataset,
        "selection_rule": "Policies are fixed before evaluation; no future labels are used to select a policy.",
        "parameters": {
            "future_bars": 4,
            "transaction_cost_bps": 4.0,
            "fast_period": 20,
            "slow_period": 50,
            "folds": 4,
        },
        "policies": [item.to_dict() for item in metrics],
        "causal_rule": "All policy directions use current/past closes only; future close movement is evaluation-only.",
        "status": "report_only",
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
