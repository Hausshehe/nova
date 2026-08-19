from __future__ import annotations

import json
import sys
from pathlib import Path

from trading_research.data import load_csv
from trading_research.walkforward_regime_learner import evaluate_walkforward_regime_direction


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run_walkforward_regime_learner.py DATASET OUTPUT_JSON")
        return 2
    dataset, output = sys.argv[1:]
    bars = load_csv(dataset)
    result = evaluate_walkforward_regime_direction(bars)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps({"dataset": dataset, **result}, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "predictions"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
