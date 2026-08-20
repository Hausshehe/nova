from trading_research.data import Bar
from trading_research.experiment2 import (
    build_basic_features,
    class_balance,
    make_walk_forward_windows,
    standardize_fit_transform,
)
from datetime import datetime, timezone


def _bars(n: int = 40) -> list[Bar]:
    return [
        Bar(
            timestamp=datetime(2020, 1, 1 + i, tzinfo=timezone.utc),
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=1000.0,
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
    changed[20].close += 1000.0
    changed_features = build_basic_features(changed, prediction_horizon=1, short_window=5, long_window=20)
    # The row at bar 19 must not use bar 20 in its feature vector.
    assert baseline[0].values == changed_features[0].values


def test_walk_forward_windows_are_ordered_and_disjoint() -> None:
    windows = make_walk_forward_windows(
        100, train_size=50, validation_size=20, test_size=10, step=10
    )
    assert windows
    assert windows[0].train_end == windows[0].validation_start
    assert windows[0].validation_end == windows[0].test_start
    assert windows[0].test_end <= windows[1].train_end if len(windows) > 1 else True
    for left, right in zip(windows, windows[1:]):
        assert left.test_start < left.test_end <= right.test_end
        assert right.train_start > left.train_start


def test_standardization_uses_train_statistics_only() -> None:
    train = [[0.0], [1.0], [2.0]]
    transformed = standardize_fit_transform(train, [[1.0], [2.0], [100.0]])
    assert transformed[0][0] < transformed[1][0] < transformed[2][0]
    assert abs(transformed[0][0] + transformed[1][0]) < 1.0


def test_class_balance() -> None:
    assert class_balance([-0.1, 0.0, 0.2, 0.3]) == (2, 2)
