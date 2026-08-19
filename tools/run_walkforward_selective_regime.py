from __future__ import annotations

import json
import sys
from pathlib import Path

from trading_research.data import load_csv
from trading_research.walkforward_regime_selective import evaluate_walkforward_selective_regime


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: run_walkforward_selective_regime.py DATASET OUTPUT")
    dataset, output = sys.argv[1:]
    bars = load_csv(Path(dataset))
    report = evaluate_walkforward_selective_regime(bars)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
