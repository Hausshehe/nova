"""Run the frozen volatility mean-reversion hypothesis once and emit compact JSON."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .experiment import run_experiment
from .volatility_mean_reversion import HYPOTHESIS, signal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--output", default="volatility_mean_reversion_experiment.json")
    parser.add_argument("--fee-bps", type=float, default=1.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    args = parser.parse_args()

    record = run_experiment(
        csv_path=args.csv_path,
        hypothesis=HYPOTHESIS,
        signal=signal,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        strategy_version="volatility-mr-20-2z-v1",
    )
    payload = record.to_dict()
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)

    print(json.dumps({
        "hypothesis": HYPOTHESIS.name,
        "decision": record.final_decision.value,
        "dataset": record.dataset,
        "dataset_sha256": record.dataset_sha256,
        "segments": {
            segment["name"]: {
                "bars": segment["bars"],
                "start": segment["start"],
                "end": segment["end"],
                "decision": segment["decision"]["decision"],
                "trades": segment["metrics"]["trades"],
                "net_return": segment["metrics"]["net_return"],
                "max_drawdown": segment["metrics"]["max_drawdown"],
                "profit_factor": segment["metrics"]["profit_factor"],
                "expectancy": segment["metrics"]["expectancy"],
                "win_rate": segment["metrics"]["win_rate"],
            }
            for segment in payload["segments"]
        }
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
