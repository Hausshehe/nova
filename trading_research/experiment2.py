"""Leakage-safe primitives for Nova Experiment 2.

This module intentionally contains no model fitting or trading execution. It
provides deterministic feature construction, forward-return labels, and
chronological walk-forward windows so model research can be built on top of a
well-defined anti-leakage foundation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Iterable, Sequence

from .data import Bar


@dataclass(frozen=True)
class FeatureRow:
    """Features and a future label anchored to one historical bar."""

    timestamp: object
    values: tuple[float, ...]
    target_return: float


@dataclass(frozen=True)
class WalkForwardWindow:
    """One train/validation/test window in chronological order."""

    train_start: int
    train_end: int
    validation_start: int
    validation_end: int
    test_start: int
    test_end: int


def _safe_log_return(current: float, previous: float) -> float:
    if current <= 0 or previous <= 0:
        raise ValueError("prices must be positive for log returns")
    return log(current / previous)


def _rolling_mean(values: Sequence[float], end: int, window: int) -> float:
    start = end - window + 1
    if start < 0:
        raise ValueError("insufficient history")
    return sum(values[start : end + 1]) / window


def _rolling_std(values: Sequence[float], end: int, window: int) -> float:
    start = end - window + 1
    if start < 0:
        raise ValueError("insufficient history")
    sample = values[start : end + 1]
    mean = sum(sample) / window
    variance = sum((x - mean) ** 2 for x in sample) / window
    return variance ** 0.5


def build_basic_features(
    bars: Sequence[Bar],
    *,
    prediction_horizon: int = 1,
    short_window: int = 5,
    long_window: int = 20,
) -> list[FeatureRow]:
    """Build strictly causal features and future-return labels.

    For row ``t`` every feature uses bars up to ``t`` only. The target uses
    ``close[t + prediction_horizon] / close[t] - 1`` and therefore cannot leak
    into the feature vector.
    """
    if prediction_horizon < 1:
        raise ValueError("prediction_horizon must be >= 1")
    if short_window < 2 or long_window <= short_window:
        raise ValueError("require 2 <= short_window < long_window")
    if len(bars) <= long_window + prediction_horizon:
        raise ValueError("insufficient bars")

    closes = [bar.close for bar in bars]
    ranges = [
        (bar.high - bar.low) / bar.close if bar.close else 0.0
        for bar in bars
    ]

    rows: list[FeatureRow] = []
    first = long_window - 1
    last = len(bars) - prediction_horizon - 1

    for index in range(first, last + 1):
        lag1 = _safe_log_return(closes[index], closes[index - 1])
        lag5 = _safe_log_return(closes[index], closes[index - short_window])
        short_mean = _rolling_mean(closes, index, short_window)
        long_mean = _rolling_mean(closes, index, long_window)
        volatility = _rolling_std(closes, index, long_window)
        mean_gap = (short_mean / long_mean) - 1.0 if long_mean else 0.0
        range_now = ranges[index]
        range_mean = _rolling_mean(ranges, index, short_window)

        future = closes[index + prediction_horizon]
        target_return = (future / closes[index]) - 1.0

        rows.append(
            FeatureRow(
                timestamp=bars[index].timestamp,
                values=(
                    lag1,
                    lag5,
                    mean_gap,
                    volatility / closes[index] if closes[index] else 0.0,
                    range_now,
                    range_mean,
                ),
                target_return=target_return,
            )
        )

    return rows


def make_walk_forward_windows(
    n_rows: int,
    *,
    train_size: int,
    validation_size: int,
    test_size: int,
    step: int | None = None,
) -> list[WalkForwardWindow]:
    """Construct expanding/rolling chronological windows without shuffling."""
    if min(n_rows, train_size, validation_size, test_size) <= 0:
        raise ValueError("all sizes must be positive")
    step = test_size if step is None else step
    if step <= 0:
        raise ValueError("step must be positive")

    windows: list[WalkForwardWindow] = []
    start = 0
    while start + train_size + validation_size + test_size <= n_rows:
        train_end = start + train_size
        validation_end = train_end + validation_size
        test_end = validation_end + test_size
        windows.append(
            WalkForwardWindow(
                train_start=start,
                train_end=train_end,
                validation_start=train_end,
                validation_end=validation_end,
                test_start=validation_end,
                test_end=test_end,
            )
        )
        start += step
    return windows


def standardize_fit_transform(
    train: Sequence[Sequence[float]],
    values: Sequence[Sequence[float]],
) -> list[list[float]]:
    """Fit feature normalization on train data only, then transform values."""
    if not train:
        raise ValueError("train must not be empty")
    width = len(train[0])
    if width == 0 or any(len(row) != width for row in train):
        raise ValueError("train rows must have consistent non-zero width")
    if any(len(row) != width for row in values):
        raise ValueError("values rows must match train width")

    means = [sum(row[col] for row in train) / len(train) for col in range(width)]
    stds: list[float] = []
    for col in range(width):
        variance = sum((row[col] - means[col]) ** 2 for row in train) / len(train)
        stds.append(variance ** 0.5 or 1.0)

    return [
        [(row[col] - means[col]) / stds[col] for col in range(width)]
        for row in values
    ]


def class_balance(target_returns: Iterable[float], threshold: float = 0.0) -> tuple[int, int]:
    """Return counts of observations at/below and above a classification threshold."""
    down_or_equal = 0
    up = 0
    for value in target_returns:
        if value > threshold:
            up += 1
        else:
            down_or_equal += 1
    return down_or_equal, up
