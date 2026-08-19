from __future__ import annotations

import argparse
import json

from trading_research.data import load_csv
from trading_research.horizon_adaptation_ablation import evaluate_horizon_adaptation_ablation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()
    result = evaluate_horizon_adaptation_ablation(load_csv(args.dataset))
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
