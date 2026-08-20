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
from statistics import mean

from .data import load_csv
from .dukascopy_history import INSTRUMENTS, TIMEFRAMES
from .experiment2 import build_basic_features, standardize_fit_transform
from .predictive_benchmark import brier_score, directional_accuracy, fit_probability_model, log_loss, predict_rows

# Pre-declared development contract. These values are not tuned after observing data.
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


def _metrics(predictions, baseline_predictions, rows, indices):
    model_direction = [1 if p.probability_up >= 0.5 else 0 for p in predictions]
    model_trade = [
        1 if p.probability_up >= TRADE_THRESHOLD else -1 if p.probability_up <= 1.0 - TRADE_THRESHOLD else 0
        for p in predictions
    ]
    targets = [1 if rows[i].target_return > 0 else 0 for i in indices]
    model_accuracy = mean(int(p == t) for p, t in zip(model_direction, targets))
    majority_accuracy = mean(int(p == t) for p, t in zip(baseline_predictions['majority'], targets))
    last_accuracy = mean(int(p == t) for p, t in zip(baseline_predictions['last_return'], targets))
    trend_accuracy = mean(int(p == t) for p, t in zip(baseline_predictions['trend'], targets))

    def net_return(preds):
        return sum(_net_trade_return(p, rows[i].target_return) for p, i in zip(preds, indices))

    traded_pairs = [(side, i) for side, i in zip(model_trade, indices) if side != 0]
    model_net = sum(
        _net_trade_return(1 if side == 1 else 0, rows[i].target_return)
        for side, i in traded_pairs
    )
    model_hit_rate = mean(
        1.0 if _directional_return(1 if side == 1 else 0, rows[i].target_return) > ROUND_TRIP_COST else 0.0
        for side, i in traded_pairs
    ) if traded_pairs else 0.0

    return {
        'model_accuracy': model_accuracy,
        'majority_accuracy': majority_accuracy,
        'last_return_accuracy': last_accuracy,
        'trend_accuracy': trend_accuracy,
        'model_brier': brier_score(predictions),
        'model_log_loss': log_loss(predictions),
        'model_net_return': model_net,
        'majority_net_return': net_return(baseline_predictions['majority']),
        'last_return_net_return': net_return(baseline_predictions['last_return']),
        'trend_net_return': net_return(baseline_predictions['trend']),
        'model_trades': len(traded_pairs),
        'model_trade_hit_rate': model_hit_rate,
        'model_abstention_rate': 1.0 - (len(traded_pairs) / len(indices)),
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

        train_x = [rows[i].values for i in train_idx]
        validation_x = [rows[i].values for i in validation_idx]
        train_scaled = standardize_fit_transform(train_x, train_x)
        validation_scaled = standardize_fit_transform(train_x, validation_x)

        class Proxy:
            def __init__(self, row, values):
                self.timestamp = row.timestamp
                self.values = tuple(values)
                self.target_return = row.target_return

        scaled_train_rows = [Proxy(rows[i], values) for i, values in zip(train_idx, train_scaled)]
        model = fit_probability_model(scaled_train_rows, tuple(range(len(scaled_train_rows))))
        scaled_validation_rows = [Proxy(rows[i], values) for i, values in zip(validation_idx, validation_scaled)]
        local_predictions = predict_rows(model, scaled_validation_rows, tuple(range(len(scaled_validation_rows))))
        predictions = [
            type(p)(
                index=validation_idx[p.index],
                timestamp=p.timestamp,
                probability_up=p.probability_up,
                target_up=p.target_up,
                target_return=p.target_return,
            )
            for p in local_predictions
        ]

        baseline_predictions = {'majority': [], 'last_return': [], 'trend': []}
        train_targets = [1 if rows[i].target_return > 0 else 0 for i in train_idx]
        majority = 1 if mean(train_targets) >= 0.5 else 0
        for i in validation_idx:
            baseline_predictions['majority'].append(majority)
            baseline_predictions['last_return'].append(1 if rows[i].values[0] > 0 else 0)
            baseline_predictions['trend'].append(1 if rows[i].values[2] > 0 else 0)

        results.append(FoldResult(
            instrument=instrument,
            timeframe=timeframe,
            fold=fold_no,
            train_rows=len(train_idx),
            validation_rows=len(validation_idx),
            **_metrics(predictions, baseline_predictions, rows, validation_idx),
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

    if len({(r.instrument, r.timeframe) for r in all_results}) != len(expected):
        raise SystemExit(f'development_universe_incomplete:{len({(r.instrument, r.timeframe) for r in all_results})}/{len(expected)}:{skipped}')

    csv_path = output_dir / 'experiment2_development_results.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(all_results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in all_results)

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
        'mean_model_accuracy': mean(r.model_accuracy for r in all_results),
        'mean_majority_accuracy': mean(r.majority_accuracy for r in all_results),
        'mean_model_net_return': mean(r.model_net_return for r in all_results),
        'mean_best_baseline_net_return': mean(max(r.majority_net_return, r.last_return_net_return, r.trend_net_return) for r in all_results),
        'skipped': skipped,
    }
    (output_dir / 'experiment2_development_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (output_dir / 'experiment2_development_report.md').write_text(
        '# Experiment 2 Development Benchmark\n\n'
        'This is a pre-test development evaluation. The final chronological 20% was not scored.\n\n'
        f'- Contexts evaluated: {summary["contexts_evaluated"]}/{summary["contexts_expected"]}\n'
        f'- Expanding folds: {len(DEV_FOLDS)}\n'
        f'- Round-trip cost: {ROUND_TRIP_COST:.4%}\n'
        f'- Fixed trading threshold: {TRADE_THRESHOLD:.2f}\n'
        f'- Mean model accuracy: {summary["mean_model_accuracy"]:.4f}\n'
        f'- Mean majority accuracy: {summary["mean_majority_accuracy"]:.4f}\n'
        f'- Mean model net return per bar: {summary["mean_model_net_return"]:.6f}\n'
        f'- Mean best-baseline net return per bar: {summary["mean_best_baseline_net_return"]:.6f}\n\n'
        'No final-test classification is made by this benchmark. Candidate promotion requires the protocol gates to be reviewed before any final-test run.\n',
        encoding='utf-8',
    )
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('data/research/universe_v2'))
    parser.add_argument('--output-dir', type=Path, default=Path('data/research/experiment2_development'))
    args = parser.parse_args()
    run(args.root, args.output_dir)


if __name__ == '__main__':
    main()
