from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_research.data import load_csv
from trading_research.directional_signal_comparison import compare_directional_signals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()
    bars = load_csv(args.dataset)
    results = compare_directional_signals(bars)
    payload = {
        "schema_version": 1,
        "policy": "predefined_causal_direction_signal_comparison",
        "dataset": args.dataset,
        "transaction_cost_bps": 4.0,
        "future_bars": 4,
        "candidate_basis": "trusted_high_recall_union_candidate",
        "selection_rule": "No signal is selected using future labels; all four signals are evaluated side-by-side.",
        "signals": [r.to_dict() for r in results],
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
