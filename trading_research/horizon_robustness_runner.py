"""CLI runner for the frozen 8-bar robustness audit.

Usage:
    python -m trading_research.horizon_robustness_runner path/to/data.csv
    python -m trading_research.horizon_robustness_runner path/to/data.csv --output audit.json

The runner only executes a pre-defined audit. It does not search parameters,
select the best configuration, or modify strategy state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .data import load_csv
from .horizon_robustness_audit import DEFAULT_COST_GRID, audit_fixed_8_vs_alternatives


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Nova's frozen 8-bar robustness audit.")
    parser.add_argument("csv_path", help="Chronological OHLCV CSV with timestamp/open/high/low/close/volume.")
    parser.add_argument("--output", help="Optional path for the JSON audit record.")
    parser.add_argument("--training-cost-bps", type=float, default=4.0)
    parser.add_argument("--half-life", type=float, default=60.0)
    parser.add_argument("--min-history", type=int, default=120)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument(
        "--cost-grid-bps",
        type=float,
        nargs="+",
        default=list(DEFAULT_COST_GRID),
        help="Evaluation-only cost grid. Decisions are not re-selected for these values.",
    )
    return parser


def run(
    csv_path: str,
    *,
    training_cost_bps: float = 4.0,
    half_life: float = 60.0,
    min_history: int = 120,
    folds: int = 4,
    cost_grid_bps: Sequence[float] = DEFAULT_COST_GRID,
) -> dict[str, object]:
    bars = load_csv(csv_path)
    result = audit_fixed_8_vs_alternatives(
        bars,
        training_cost_bps=training_cost_bps,
        cost_grid_bps=cost_grid_bps,
        half_life=half_life,
        min_history=min_history,
        folds=folds,
    )
    result["dataset"] = str(csv_path)
    result["total_bars"] = len(bars)
    result["runner"] = "horizon_robustness_runner"
    result["runner_policy"] = "fixed audit only; no parameter search or strategy promotion"
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run(
        args.csv_path,
        training_cost_bps=args.training_cost_bps,
        half_life=args.half_life,
        min_history=args.min_history,
        folds=args.folds,
        cost_grid_bps=args.cost_grid_bps,
    )
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
