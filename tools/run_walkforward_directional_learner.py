from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_research.data import load_csv
from trading_research.walkforward_directional_learner import evaluate_walkforward_adaptive_direction


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--min-train", type=int, default=240)
    args = parser.parse_args()

    bars = load_csv(args.dataset)
    result = evaluate_walkforward_adaptive_direction(
        bars,
        folds=args.folds,
        min_train=args.min_train,
    )
    result["dataset"] = args.dataset
    result["parameters"] = {
        "future_bars": 4,
        "transaction_cost_bps": 4.0,
        "folds": args.folds,
        "min_train": args.min_train,
        "features": ["sma_gap_20_50", "momentum_4", "momentum_8", "momentum_12"],
        "learner": "fixed_ridge_logistic_7_epochs_lr_0.02_l2_0.01",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "predictions"}, indent=2))


if __name__ == "__main__":
    main()
