"""Run uncertainty diagnostics on already-frozen horizon candidates.

This runner performs no model selection. It reconstructs the frozen
configurations, removes overlapping holdings, and estimates moving-block
bootstrap uncertainty for the resulting return streams.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .data import load_csv
from .horizon_robustness_audit import _all_bar_baseline_predictions, _non_overlapping
from .online_horizon_expert_ensemble import HORIZONS, collect_online_horizon_predictions
from .statistical_diagnostics import moving_block_bootstrap_mean_ci


def _net_values(predictions, cost_bps: float) -> list[float]:
    return [prediction.gross_return_bps - cost_bps for prediction in predictions]


def _diagnostic(values: Sequence[float], *, block_length: int, samples: int, seed: int) -> dict[str, object]:
    return moving_block_bootstrap_mean_ci(
        values,
        block_length=min(block_length, len(values)),
        samples=samples,
        seed=seed,
    )


def run(
    csv_path: str,
    *,
    cost_bps: float = 4.0,
    block_length: int = 5,
    samples: int = 2000,
) -> dict[str, object]:
    if cost_bps < 0:
        raise ValueError("cost_bps must be non-negative")
    if block_length <= 0 or samples <= 0:
        raise ValueError("block_length and samples must be positive")

    bars = load_csv(Path(csv_path))
    fixed_8 = collect_online_horizon_predictions(
        bars, horizons=(8,), training_cost_bps=cost_bps, half_life=60.0, min_history=120
    )
    adaptive = collect_online_horizon_predictions(
        bars, horizons=HORIZONS, training_cost_bps=cost_bps, half_life=60.0, min_history=120
    )

    streams = {
        "naive_long_8": _all_bar_baseline_predictions(bars, direction="LONG", horizon=8),
        "naive_short_8": _all_bar_baseline_predictions(bars, direction="SHORT", horizon=8),
        "online_expert_fixed_8": fixed_8,
        "online_expert_adaptive_2_4_8": adaptive,
    }
    result: dict[str, object] = {
        "policy": "frozen_non_overlapping_statistical_audit",
        "research_status": "diagnostic_only",
        "evaluation_cost_bps": cost_bps,
        "block_length": block_length,
        "bootstrap_samples": samples,
        "interpretation_guardrail": "Bootstrap intervals quantify uncertainty in frozen return streams; they do not establish statistical significance, executable PnL, or future profitability.",
        "configurations": {},
    }

    for name, predictions in streams.items():
        selected = _non_overlapping(predictions)
        values = _net_values(selected, cost_bps)
        result["configurations"][name] = {
            "decisions": len(values),
            "bootstrap": _diagnostic(values, block_length=block_length, samples=samples, seed=17),
        }

    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run frozen non-overlapping bootstrap diagnostics.")
    parser.add_argument("csv_path")
    parser.add_argument("--cost-bps", type=float, default=4.0)
    parser.add_argument("--block-length", type=int, default=5)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run(
        args.csv_path,
        cost_bps=args.cost_bps,
        block_length=args.block_length,
        samples=args.samples,
    )
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
