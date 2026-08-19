from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.directional_baseline_evaluation import evaluate_directional_baseline


def _bars(values):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(start + timedelta(minutes=i), value, value + 0.001, value - 0.001, value, 1.0)
        for i, value in enumerate(values)
    ]


def test_empty_candidate_dataset_is_safe():
    bars = _bars([1.0] * 60)
    full, folds = evaluate_directional_baseline(bars, folds=4)
    assert full.candidate_bars == 0
    assert full.evaluated_bars == 0
    assert len(folds) == 4


def test_directional_baseline_is_report_only_and_deterministic():
    values = [1.0 + i * 0.0001 for i in range(70)]
    bars = _bars(values)
    first, first_folds = evaluate_directional_baseline(bars, folds=4)
    second, second_folds = evaluate_directional_baseline(bars, folds=4)
    assert first == second
    assert first_folds == second_folds
