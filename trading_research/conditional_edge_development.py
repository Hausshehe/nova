"""Controlled development benchmark for conditional edge detection.

The final 20% of every chronological dataset remains reserved. This benchmark
asks whether a causal edge gate improves on the existing global selector while
allowing the gate to abstain when evidence is insufficient.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median

from .conditional_edge_policy import evaluate_conditional_edge_gate
from .data import load_csv
from .dukascopy_history import INSTRUMENTS, TIMEFRAMES
from .online_expert_ensemble import evaluate_online_expert_ensemble

DEVELOPMENT_FRACTION = 0.80
TRANSACTION_COST_BPS = 4.0
FUTURE_BARS = 4
HALF_LIFE = 60.0
MIN_GLOBAL_HISTORY = 120
MIN_CONTEXT_HISTORY = 40
SHRINKAGE_PRIOR = 30.0
Z_SCORE = 1.0
MIN_EDGE_BPS = 0.5
MIN_MARGIN_BPS = 0.5
FOLDS = 4
MIN_BARS = 250


@dataclass(frozen=True)
class EdgeResult:
    instrument: str
    timeframe: str
    total_bars: int
    development_bars: int
    final_reserved_bars: int
    global_decisions: int
    gate_decisions: int
    gate_abstentions: int
    global_decision_rate: float
    gate_decision_rate: float
    global_mean_net_bps: float
    gate_mean_net_bps: float
    gate_minus_global_bps: float
    global_positive_rate: float
    gate_positive_rate: float
    global_folds_positive: int
    gate_folds_positive: int


def evaluate_context(instrument: str, timeframe: str, path: Path) -> EdgeResult:
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
    gate_result = evaluate_conditional_edge_gate(
        development,
        min_context_history=MIN_CONTEXT_HISTORY,
        min_global_history=MIN_GLOBAL_HISTORY,
        shrinkage_prior=SHRINKAGE_PRIOR,
        z_score=Z_SCORE,
        min_edge_bps=MIN_EDGE_BPS,
        min_margin_bps=MIN_MARGIN_BPS,
        **kwargs,
    )
    return EdgeResult(
        instrument=instrument,
        timeframe=timeframe,
        total_bars=len(bars),
        development_bars=development_bars,
        final_reserved_bars=reserved,
        global_decisions=int(global_result["decisions"]),
        gate_decisions=int(gate_result["decisions"]),
        gate_abstentions=int(gate_result["abstentions"]),
        global_decision_rate=float(global_result["decision_rate"]),
        gate_decision_rate=float(gate_result["decision_rate"]),
        global_mean_net_bps=float(global_result["mean_net_return_bps"]),
        gate_mean_net_bps=float(gate_result["mean_net_return_bps"]),
        gate_minus_global_bps=float(gate_result["mean_net_return_bps"])
        - float(global_result["mean_net_return_bps"]),
        global_positive_rate=float(global_result["positive_net_rate"]),
        gate_positive_rate=float(gate_result["positive_net_rate"]),
        global_folds_positive=int(global_result["folds_positive"]),
        gate_folds_positive=int(gate_result["folds_positive"]),
    )


def run(root: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = [(instrument, timeframe) for instrument in INSTRUMENTS for timeframe in TIMEFRAMES]
    results: list[EdgeResult] = []
    failures: list[str] = []

    for instrument, timeframe in expected:
        path = root / f"{instrument}_{timeframe}.csv"
        if not path.is_file():
            failures.append(f"missing:{instrument}:{timeframe}")
            continue
        try:
            results.append(evaluate_context(instrument, timeframe, path))
        except Exception as exc:
            failures.append(f"error:{instrument}:{timeframe}:{type(exc).__name__}:{exc}")

    if failures:
        raise SystemExit("DEVELOPMENT_DATA_FAILURE:" + "|".join(failures))
    if len(results) != len(expected):
        raise SystemExit(f"DEVELOPMENT_UNIVERSE_INCOMPLETE:{len(results)}/{len(expected)}")

    differences = [row.gate_minus_global_bps for row in results]
    gate_better = sum(value > 0 for value in differences)
    global_better = sum(value < 0 for value in differences)
    ties = sum(value == 0 for value in differences)
    summary = {
        "status": "DEVELOPMENT_ONLY",
        "research_question": "Can a causal conditional-edge gate improve selection while abstaining when evidence is insufficient?",
        "contexts_evaluated": len(results),
        "development_fraction": DEVELOPMENT_FRACTION,
        "final_test_used": False,
        "final_reserved_fraction": 1.0 - DEVELOPMENT_FRACTION,
        "future_bars": FUTURE_BARS,
        "transaction_cost_bps": TRANSACTION_COST_BPS,
        "half_life": HALF_LIFE,
        "min_global_history": MIN_GLOBAL_HISTORY,
        "min_context_history": MIN_CONTEXT_HISTORY,
        "shrinkage_prior": SHRINKAGE_PRIOR,
        "z_score": Z_SCORE,
        "min_edge_bps": MIN_EDGE_BPS,
        "min_margin_bps": MIN_MARGIN_BPS,
        "folds": FOLDS,
        "mean_gate_net_bps": mean(row.gate_mean_net_bps for row in results),
        "mean_global_net_bps": mean(row.global_mean_net_bps for row in results),
        "mean_gate_minus_global_bps": mean(differences),
        "median_gate_minus_global_bps": median(differences),
        "contexts_gate_better": gate_better,
        "contexts_global_better": global_better,
        "contexts_tied": ties,
        "gate_better_fraction": gate_better / len(results),
        "decision_rate_mean_gate": mean(row.gate_decision_rate for row in results),
        "decision_rate_mean_global": mean(row.global_decision_rate for row in results),
        "abstention_rate_mean_gate": mean(1.0 - row.gate_decision_rate for row in results),
        "results_path": str(output_dir / "conditional_edge_development_results.csv"),
    }

    csv_path = output_dir / "conditional_edge_development_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(row) for row in results)

    (output_dir / "conditional_edge_development_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (output_dir / "conditional_edge_development_report.md").write_text(
        "# Nova Conditional Edge Development Benchmark\n\n"
        "Only the earliest 80% of each chronological dataset is evaluated. "
        "The final 20% remains reserved and is not used for selection or claims.\n\n"
        f"- Contexts evaluated: {len(results)}/{len(expected)}\n"
        f"- Mean gate net return/decision: {summary['mean_gate_net_bps']:.4f} bps\n"
        f"- Mean global net return/decision: {summary['mean_global_net_bps']:.4f} bps\n"
        f"- Mean gate advantage: {summary['mean_gate_minus_global_bps']:.4f} bps\n"
        f"- Median gate advantage: {summary['median_gate_minus_global_bps']:.4f} bps\n"
        f"- Contexts where gate is better: {gate_better}/{len(results)}\n"
        f"- Contexts where global selector is better: {global_better}/{len(results)}\n"
        f"- Ties: {ties}/{len(results)}\n"
        f"- Mean gate decision rate: {summary['decision_rate_mean_gate']:.4f}\n\n"
        "This is development evidence only. Promotion requires freezing the design and evaluating it once on the untouched final-test window.\n",
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
        default=Path("data/research/conditional_edge_development"),
    )
    args = parser.parse_args()
    run(args.root, args.output_dir)


if __name__ == "__main__":
    main()
