"""Controlled development benchmark for contextual strategy selection.

This experiment compares Nova's causal contextual expert selector with the
non-contextual causal online expert ensemble. Only the first 80% of each
chronological dataset is evaluated; the final 20% is reserved.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median

from .data import load_csv
from .dukascopy_history import INSTRUMENTS, TIMEFRAMES
from .contextual_online_expert_ensemble import evaluate_contextual_online_expert_ensemble
from .online_expert_ensemble import evaluate_online_expert_ensemble

DEVELOPMENT_FRACTION = 0.80
TRANSACTION_COST_BPS = 4.0
FUTURE_BARS = 4
HALF_LIFE = 60.0
MIN_GLOBAL_HISTORY = 120
MIN_CONTEXT_HISTORY = 30
FOLDS = 4
MIN_BARS = 250


@dataclass(frozen=True)
class ContextResult:
    instrument: str
    timeframe: str
    total_bars: int
    development_bars: int
    final_reserved_bars: int
    global_decisions: int
    contextual_decisions: int
    global_decision_rate: float
    contextual_decision_rate: float
    global_mean_net_bps: float
    contextual_mean_net_bps: float
    contextual_minus_global_bps: float
    global_positive_rate: float
    contextual_positive_rate: float
    global_folds_positive: int
    contextual_folds_positive: int
    global_fold_mean_net_bps: float
    contextual_fold_mean_net_bps: float


def _mean_or_zero(values: list[float]) -> float:
    return mean(values) if values else 0.0


def evaluate_context(instrument: str, timeframe: str, path: Path) -> ContextResult:
    bars = load_csv(path)
    if len(bars) < MIN_BARS:
        raise ValueError(f"insufficient_bars:{instrument}:{timeframe}:{len(bars)}")

    development_bars = max(1, int(len(bars) * DEVELOPMENT_FRACTION))
    development = bars[:development_bars]
    reserved = len(bars) - development_bars
    kwargs = {
        "future_bars": FUTURE_BARS,
        "transaction_cost_bps": TRANSACTION_COST_BPS,
        "half_life": HALF_LIFE,
        "folds": FOLDS,
    }

    global_result = evaluate_online_expert_ensemble(
        development,
        min_history=MIN_GLOBAL_HISTORY,
        **kwargs,
    )
    contextual_result = evaluate_contextual_online_expert_ensemble(
        development,
        min_context_history=MIN_CONTEXT_HISTORY,
        min_global_history=MIN_GLOBAL_HISTORY,
        **kwargs,
    )

    global_folds = [float(value) for value in global_result["fold_net_returns"]]
    contextual_folds = [float(value) for value in contextual_result["fold_net_returns"]]
    return ContextResult(
        instrument=instrument,
        timeframe=timeframe,
        total_bars=len(bars),
        development_bars=development_bars,
        final_reserved_bars=reserved,
        global_decisions=int(global_result["decisions"]),
        contextual_decisions=int(contextual_result["decisions"]),
        global_decision_rate=float(global_result["decision_rate"]),
        contextual_decision_rate=float(contextual_result["decision_rate"]),
        global_mean_net_bps=float(global_result["mean_net_return_bps"]),
        contextual_mean_net_bps=float(contextual_result["mean_net_return_bps"]),
        contextual_minus_global_bps=float(contextual_result["mean_net_return_bps"])
        - float(global_result["mean_net_return_bps"]),
        global_positive_rate=float(global_result["positive_net_rate"]),
        contextual_positive_rate=float(contextual_result["positive_net_rate"]),
        global_folds_positive=int(global_result["folds_positive"]),
        contextual_folds_positive=int(contextual_result["folds_positive"]),
        global_fold_mean_net_bps=_mean_or_zero(global_folds),
        contextual_fold_mean_net_bps=_mean_or_zero(contextual_folds),
    )


def run(root: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = [(instrument, timeframe) for instrument in INSTRUMENTS for timeframe in TIMEFRAMES]
    results: list[ContextResult] = []
    failures: list[str] = []

    for instrument, timeframe in expected:
        path = root / f"{instrument}_{timeframe}.csv"
        if not path.is_file():
            failures.append(f"missing:{instrument}:{timeframe}")
            continue
        try:
            results.append(evaluate_context(instrument, timeframe, path))
        except Exception as exc:  # pragma: no cover - surfaced as evidence failure
            failures.append(f"error:{instrument}:{timeframe}:{type(exc).__name__}:{exc}")

    if failures:
        raise SystemExit("DEVELOPMENT_DATA_FAILURE:" + "|".join(failures))
    if len(results) != len(expected):
        raise SystemExit(f"DEVELOPMENT_UNIVERSE_INCOMPLETE:{len(results)}/{len(expected)}")

    differences = [row.contextual_minus_global_bps for row in results]
    contextual_better = sum(value > 0 for value in differences)
    global_better = sum(value < 0 for value in differences)
    ties = sum(value == 0 for value in differences)
    mean_difference = mean(differences)

    summary = {
        "status": "DEVELOPMENT_ONLY",
        "research_question": "Does observable context improve causal expert selection over the global causal selector?",
        "contexts_evaluated": len(results),
        "development_fraction": DEVELOPMENT_FRACTION,
        "final_test_used": False,
        "final_reserved_fraction": 1.0 - DEVELOPMENT_FRACTION,
        "future_bars": FUTURE_BARS,
        "transaction_cost_bps": TRANSACTION_COST_BPS,
        "half_life": HALF_LIFE,
        "min_global_history": MIN_GLOBAL_HISTORY,
        "min_context_history": MIN_CONTEXT_HISTORY,
        "folds": FOLDS,
        "mean_contextual_net_bps": mean(row.contextual_mean_net_bps for row in results),
        "mean_global_net_bps": mean(row.global_mean_net_bps for row in results),
        "mean_contextual_minus_global_bps": mean_difference,
        "median_contextual_minus_global_bps": median(differences),
        "contexts_contextual_better": contextual_better,
        "contexts_global_better": global_better,
        "contexts_tied": ties,
        "contextual_better_fraction": contextual_better / len(results),
        "decision_rate_mean_contextual": mean(row.contextual_decision_rate for row in results),
        "decision_rate_mean_global": mean(row.global_decision_rate for row in results),
        "results_path": str(output_dir / "context_selector_development_results.csv"),
    }

    csv_path = output_dir / "context_selector_development_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(row) for row in results)

    (output_dir / "context_selector_development_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (output_dir / "context_selector_development_report.md").write_text(
        "# Nova Context Selector Development Benchmark\n\n"
        "This benchmark evaluates only the earliest 80% of each chronological dataset. "
        "The final 20% remains reserved and is not used for selection or claims.\n\n"
        f"- Contexts evaluated: {len(results)}/{len(expected)}\n"
        f"- Mean contextual net return/decision: {summary['mean_contextual_net_bps']:.4f} bps\n"
        f"- Mean global net return/decision: {summary['mean_global_net_bps']:.4f} bps\n"
        f"- Mean contextual advantage: {summary['mean_contextual_minus_global_bps']:.4f} bps\n"
        f"- Median contextual advantage: {summary['median_contextual_minus_global_bps']:.4f} bps\n"
        f"- Contexts where contextual selector is better: {contextual_better}/{len(results)}\n"
        f"- Contexts where global selector is better: {global_better}/{len(results)}\n"
        f"- Ties: {ties}/{len(results)}\n\n"
        "This is development evidence only. A positive result does not establish a final trading edge. "
        "Promotion requires a frozen follow-up experiment and an untouched final-test evaluation.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/research/universe_v2"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/research/context_selector_development"),
    )
    args = parser.parse_args()
    run(args.root, args.output_dir)


if __name__ == "__main__":
    main()
