"""Run the report-only causal directional baseline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from trading_research.data import load_csv
from trading_research.directional_baseline import build_directional_outcomes, summarize_directional_outcomes


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: run_directional_baseline.py DATASET OUTPUT_JSON")
    dataset, output = sys.argv[1:]
    bars = load_csv(dataset)
    future_bars = 4
    target_bps = 30.0
    cost_bps = 4.0
    fast_period = 20
    slow_period = 50
    outcomes = build_directional_outcomes(
        bars,
        future_bars=future_bars,
        target_bps=target_bps,
        transaction_cost_bps_round_trip=cost_bps,
        fast_period=fast_period,
        slow_period=slow_period,
    )

    folds = 4
    n = len(bars)
    fold_size = n // folds
    fold_reports = []
    for fold in range(folds):
        start = fold * fold_size
        end = n if fold == folds - 1 else (fold + 1) * fold_size
        fold_outcomes = tuple(item for item in outcomes if start <= item.index < end)
        fold_reports.append({"fold": fold + 1, "range": [start, end], **summarize_directional_outcomes(fold_outcomes)})

    report = {
        "schema_version": 1,
        "policy": "causal_sma_directional_baseline_report_only",
        "dataset": dataset,
        "parameters": {
            "future_bars": future_bars,
            "target_bps": target_bps,
            "transaction_cost_bps_round_trip": cost_bps,
            "fast_period": fast_period,
            "slow_period": slow_period,
            "folds": folds,
        },
        "full_sample": summarize_directional_outcomes(outcomes),
        "chronological_folds": fold_reports,
        "causal_rule": "Direction is determined from current/past closes only; future OHLC is evaluation-only.",
        "execution_status": "report_only",
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
