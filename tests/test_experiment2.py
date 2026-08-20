from datetime import datetime, timedelta, timezone

import pytest

from trading_research.data import Bar
from trading_research.experiment2 import (
    build_basic_features,
    class_balance,
    make_walk_forward_windows,
    standardize_fit_transform,
)
from trading_research.predictive_benchmark import (
    brier_score,
    directional_accuracy,
    fit_probability_model,
    log_loss,
    make_final_holdout,
    positive_rate,
    predict_rows,
)


def _bars(n: int = 80) -> list[Bar]:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=1000.0,
        )
        for i in range(n)
    ]


def _mixed_bars(n: int = 100) -> list[Bar]:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    closes = [100.0 + (1.0 if i % 2 == 0 else -1.0) * (1.0 + (i % 5) * 0.1) for i in range(n)]
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=closes[i],
            high=closes[i] + 1.0,
            low=closes[i] - 1.0,
            close=closes[i],
            volume=1000.0 + i,
        )
        for i in range(n)
    ]


def test_features_are_causal_and_labels_use_future_close() -> None:
    bars = _bars()
    rows = build_basic_features(bars, prediction_horizon=1, short_window=5, long_window=20)
    assert rows
    first = rows[0]
    source_index = 19
    assert first.timestamp == bars[source_index].timestamp
    expected_target = bars[source_index + 1].close / bars[source_index].close - 1.0
    assert first.target_return == expected_target


def test_future_change_does_not_alter_current_features() -> None:
    bars = _bars()
    baseline = build_basic_features(bars, prediction_horizon=1, short_window=5, long_window=20)
    changed = list(bars)
    changed[20] = Bar(
        timestamp=changed[20].timestamp,
        open=changed[20].open,
        high=changed[20].high,
        low=changed[20].low,
        close=changed[20].close + 1000.0,
        volume=changed[20].volume,
    )
    changed_features = build_basic_features(changed, prediction_horizon=1, short_window=5, long_window=20)
    assert baseline[0].values == changed_features[0].values


def test_walk_forward_windows_are_ordered_and_chronological() -> None:
    windows = make_walk_forward_windows(
        100, train_size=50, validation_size=20, test_size=10, step=10
    )
    assert windows
    for window in windows:
        assert window.train_start < window.train_end <= window.validation_start
        assert window.validation_start < window.validation_end <= window.test_start
        assert window.test_start < window.test_end
    assert windows[0].train_start < windows[1].train_start
    assert windows[0].test_start < windows[1].test_start


def test_standardization_uses_train_statistics_only() -> None:
    train = [[0.0], [1.0], [2.0]]
    transformed = standardize_fit_transform(train, [[1.0], [2.0], [100.0]])
    assert transformed[0][0] == pytest.approx(0.0)
    assert transformed[0][0] < transformed[1][0] < transformed[2][0]


def test_class_balance() -> None:
    assert class_balance([-0.1, 0.0, 0.2, 0.3]) == (2, 2)


def test_final_holdout_is_chronological_and_disjoint() -> None:
    split = make_final_holdout(100, 0.20)
    assert split.development[-1] < split.final_test[0]
    assert set(split.development).isdisjoint(split.final_test)
    assert len(split.final_test) == 20


def test_probability_model_predicts_only_requested_rows() -> None:
    rows = build_basic_features(_mixed_bars(), prediction_horizon=1, short_window=5, long_window=20)
    train = tuple(range(0, 40))
    test = tuple(range(40, 55))
    model = fit_probability_model(rows, train)
    predictions = predict_rows(model, rows, test)
    assert [p.index for p in predictions] == list(test)
    assert all(0.0 <= p.probability_up <= 1.0 for p in predictions)


def test_prediction_metrics_have_valid_ranges() -> None:
    rows = build_basic_features(_mixed_bars(), prediction_horizon=1, short_window=5, long_window=20)
    model = fit_probability_model(rows, tuple(range(0, 40)))
    predictions = predict_rows(model, rows, tuple(range(40, 60)))
    assert 0.0 <= brier_score(predictions) <= 1.0
    assert log_loss(predictions) >= 0.0
    assert 0.0 <= directional_accuracy(predictions) <= 1.0
    assert 0.0 <= positive_rate(predictions) <= 1.0
