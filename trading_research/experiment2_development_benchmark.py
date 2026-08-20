"""Pre-test development benchmark for Nova Experiment 2.

This module evaluates one pre-declared logistic model against simple direction
baselines using only the first 80% of each dataset. The final 20% is never
scored or used for model selection. It is intentionally a development tool,
not a final-test runner.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from typing import Sequence

from .data import load_csv
from .dukascopy_history import INSTRUMENTS, TIMEFRAMES
from .experiment2 import build_basic_features, standardize_fit_transform
from .predictive_benchmark import (
    brier_score,
    directional_accuracy,
    fit_probability_model,
    log_loss,
    predict_rows,
)

# Pre-declared development contract. These are not tuned after observing data.
DEV_FOLDS = ((0.40, 0.60), (0.50, 0.70), (0.60, 0.80))
ROUND_TRIP_COST = 0.0004  # 1 bp fee + 1 bp slippage per side.
TRADE_THRESHOLD = 0.55
MIN_ROWS = 200


@dataclass(frozen=True)
class FoldResult:
    instrument: str
    timeframe: str
    fold: int
    train_rows: int
    validation_rows: int
    model_accuracy: float
    majority_accuracy: float
    last_return_accuracy: float
    trend_accuracy: float
    model_brier: float
    model_log_loss: float
    model_net_return: float
    majority_net_return: float
    last_return_net_return: float
    trend_net_return: float
    model_trades: int
    model_trade_hit_rate: float
    model_abstention_rate: float


def _directional_return(prediction: int, target_return: float) -> float:
    return target_return if prediction == 1 else -target_return


def _net_trade_return(prediction: int, target_return: float) -> float:
    return _directional_return(prediction, target_return) - ROUND_TRIP_COST


def _metrics(predictions, baseline_predictions: dict[str, list[int]], rows, indices):
    model_preds = [1 if p.probability_up >= TRADE_THRESHOLD else 0 for p in predictions]
    # Accuracy is evaluated at the model's fixed 0.5 direction threshold;
    # trading uses the separate pre-declared 0.55 abstention threshold.
    model_accuracy = directional_accuracy(predictions)
    targets = [1 if rows[i].target_return > 0 else 0 for i in indices]
    majority_accuracy = mean(int(p == t) for p, t in zip(baseline_predictions['majority'], targets))
    last_accuracy = mean(int(p == t) for p, t in zip(baseline_predictions['last_return'], targets))
    trend_accuracy = mean(int(p == t) for p, t in zip(baseline_predictions['trend'], targets))

    def trade_stats(preds: Sequence[int]):
        traded = [
            _net_trade_return(p, rows[i].target_return)
            for p, i in zip(preds, indices)
            if p is not None
        ]
        return sum(traded), len(traded), (mean(1.0 if x > -ROUND_TRIP_COST else 0.0 for x in traded) if traded else 0.0)

    model_trades = [
        p for p in model_preds
        if p is not None
    ]
    model_net = sum(_net_trade_return(p, rows[i].target_return) for p, i in zip(model_preds, indices))

    def baseline_net(preds):
        return sum(_net_trade_return(p, rows[i].target_return) for p, i in zip(preds, indices))

    return {
        'model_accuracy': model_accuracy,
        'majority_accuracy': majority_accuracy,
        'last_return_accuracy': last_accuracy,
        'trend_accuracy': trend_accuracy,
        'model_brier': brier_score(predictions),
        'model_log_loss': log_loss(predictions),
        'model_net_return': model_net,
        'majority_net_return': baseline_net(baseline_predictions['majority']),
        'last_return_net_return': baseline_net(baseline_predictions['last_return']),
        'trend_net_return': baseline_net(baseline_predictions['trend']),
        'model_trades': len(model_trades),
        'model_trade_hit_rate': mean(
            1.0 if _directional_return(p, rows[i].target_return) > ROUND_TRIP_COST else 0.0
            for p, i in zip(model_preds, indices)
        ),
        'model_abstention_rate': 1.0 - (len(model_trades) / len(indices)),
    }


def evaluate_context(instrument: str, timeframe: str, path: Path) -> list[FoldResult]:
    bars = load_csv(path)
    if len(bars) < MIN_ROWS:
        raise ValueError(f'insufficient_bars:{instrument}:{timeframe}:{len(bars)}')
    rows = build_basic_features(bars, prediction_horizon=1, short_window=5, long_window=20)
    n = len(rows)
    results: list[FoldResult] = []

    for fold_no, (train_end_frac, validation_end_frac) in enumerate(DEV_FOLDS, 1):
        train_end = int(n * train_end_frac)
        validation_end = int(n * validation_end_frac)
        train_idx = tuple(range(train_end))
        validation_idx = tuple(range(train_end, validation_end))
        if len(validation_idx) < 20:
            raise ValueError(f'validation_too_small:{instrument}:{timeframe}:{len(validation_idx)}')

        # Fit normalization on train only. The current model itself is fixed;
        # the transformed values are used to avoid scale sensitivity.
        train_x = [rows[i].values for i in train_idx]
        validation_x = [rows[i].values for i in validation_idx]
        train_scaled = standardize_fit_transform(train_x, train_x)
        validation_scaled = standardize_fit_transform(train_x, validation_x)

        # Build lightweight row proxies so the existing model primitive can be
        # reused without modifying its API or touching the final test period.
        class Proxy:
            def __init__(self, row, values):
                self.timestamp = row.timestamp
                self.values = tuple(values)
                self.target_return = row.target_return

        scaled_rows = [Proxy(row, values) for row, values in zip(rows, train_scaled)]
        model = fit_probability_model(scaled_rows, tuple(range(len(train_scaled))))
        validation_rows = [Proxy(rows[i], values) for i, values in zip(validation_idx, validation_scaled)]
        predictions = predict_rows(model, validation_rows, tuple(range(len(validation_rows))))
        # Re-map prediction indices to the original validation rows.
        predictions = [
            type(p)(index=validation_idx[p.index], timestamp=p.timestamp,
                    probability_up=p.probability_up,
                    target_up=p.target_up,
                    target_return=p.target_return)
            for p in predictions
        ]

        baseline_predictions = {
            'majority': [],
            'last_return': [],
            'trend': [],
        }
        train_targets = [1 if rows[i].target_return > 0 else 0 for i in train_idx]
        majority = 1 if mean(train_targets) >= 0.5 else 0
        for i in validation_idx:
            baseline_predictions['majority'].append(majority)
            baseline_predictions['last_return'].append(1 if rows[i].values[0] > 0 else 0)
            baseline_predictions['trend'].append(1 if rows[i].values[2] > 0 else 0)

        metrics = _metrics(predictions, baseline_predictions, rows, validation_idx)
        results.append(FoldResult(
            instrument=instrument,
            timeframe=timeframe,
            fold=fold_no,
            train_rows=len(train_idx),
            validation_rows=len(validation_idx),
            **metrics,
        ))
    return results


def run(root: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[FoldResult] = []
    skipped: list[str] = []
    expected = [(instrument, timeframe) for instrument in INSTRUMENTS for timeframe in TIMEFRAMES]

    for instrument, timeframe in expected:
        path = root / f'{instrument}_{timeframe}.csv'
        if not path.is_file():
            skipped.append(f'missing:{instrument}:{timeframe}')
            continue
        all_results.extend(evaluate_context(instrument, timeframe, path))

    if not all_results:
        raise SystemExit('no_development_results')

    csv_path = output_dir / 'experiment2_development_results.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(all_results[0]).keys()))
        writer.writeheader()
        for result in all_results:
            writer.writerow(asdict(result))

    model_accuracy = mean(r.model_accuracy for r in all_results)
    majority_accuracy = mean(r.majority_accuracy for r in all_results)
    model_net = mean(r.model_net_return for r in all_results)
    best_baseline_net = mean(max(r.majority_net_return, r.last_return_net_return, r.trend_net_return) for r in all_results)

    summary = {
        'status': 'DEVELOPMENT_ONLY',
        'contexts_expected': len(expected),
        'contexts_evaluated': len({(r.instrument, r.timeframe) for r in all_results}),
        'folds_per_context': len(DEV_FOLDS),
        'final_test_used': False,
        'final_test_fraction_reserved': 0.20,
        'round_trip_cost': ROUND_TRIP_COST,
        'trade_threshold': TRADE_THRESHOLD,
        'model': 'LogisticRegression(C=1.0, penalty=l2, solver=liblinear)',
        'mean_model_accuracy': model_accuracy,
        'mean_majority_accuracy': majority_accuracy,
        'mean_model_net_return': model_net,
        'mean_best_baseline_net_return': best_baseline_net,
        'skipped': skipped,
    }
    (output_dir / 'experiment2_development_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

    report = [
        '# Experiment 2 Development Benchmark',
        '',
        'This is a pre-test development evaluation. The final chronological 20% was not scored.',
        '',
        f'- Contexts evaluated: {summary["contexts_evaluated"]}/{summary["contexts_expected"]}',
        f'- Expanding folds: {len(DEV_FOLDS)}',
        f'- Round-trip cost: {ROUND_TRIP_COST:.4%}',
        f'- Fixed trading threshold: {TRADE_THRESHOLD:.2f}',
        f'- Mean model accuracy: {model_accuracy:.4f}',
        f'- Mean majority accuracy: {majority_accuracy:.4f}',
        f'- Mean model net return per bar: {model_net:.6f}',
        f'- Mean best-baseline net return per bar: {best_baseline_net:.6f}',
        '',
        'No final-test classification is made by this benchmark. Candidate promotion requires the protocol gates to be reviewed before any final-test run.',
    ]
    (output_dir / 'experiment2_development_report.md').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('data/research/universe_v2'))
    parser.add_argument('--output-dir', type=Path, default=Path('data/research/experiment2_development'))
    args = parser.parse_args()
    run(args.root, args.output_dir)


if __name__ == '__main__':
    main()
