"""Run the frozen Donchian breakout hypothesis once and emit compact JSON."""

from __future__ import annotations

import argparse
import json

from .donchian_breakout import HYPOTHESIS, signal
from .experiment import run_experiment
from .memory import ExperienceStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--output", default="donchian_breakout_experiment.json")
    parser.add_argument("--memory-db", default="data/research/nova_experience.sqlite3")
    parser.add_argument("--fee-bps", type=float, default=1.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    args = parser.parse_args()

    memory = ExperienceStore(args.memory_db)
    record = run_experiment(
        csv_path=args.csv_path,
        hypothesis=HYPOTHESIS,
        signal=signal,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        strategy_version="donchian-55-20-v1",
        memory_store=memory,
    )
    payload = record.to_dict()
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)

    print(json.dumps({
        "hypothesis": HYPOTHESIS.name,
        "decision": record.final_decision.value,
        "dataset": record.dataset,
        "dataset_sha256": record.dataset_sha256,
        "costs": record.costs,
        "memory_db": args.memory_db,
        "segments": {
            segment["name"]: {
                "bars": segment["bars"],
                "start": segment["start"],
                "end": segment["end"],
                "decision": segment["decision"]["decision"],
                "reasons": segment["decision"]["reasons"],
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
