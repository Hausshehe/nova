"""Walk-forward predictive benchmarks for Nova Experiment 2.

The module separates development-time walk-forward evaluation from the final
chronological holdout. No final-test selection logic belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Sequence

from sklearn.linear_model import LogisticRegression


@dataclass(frozen=True)
class Prediction:
    index: int
    timestamp: object
    probability_up: float
    target_up: int
    target_return: float


@dataclass(frozen=True)
class HoldoutSplit:
    development: tuple[int, ...]
    final_test: tuple[int, ...]


def make_final_holdout(n_rows: int, test_fraction: float = 0.20) -> HoldoutSplit:
    if n_rows < 20:
        raise ValueError("n_rows is too small for a meaningful holdout")
    if not 0.0 < test_fraction < 0.5:
        raise ValueError("test_fraction must be between 0 and 0.5")
    cut = int(n_rows * (1.0 - test_fraction))
    if cut <= 0 or cut >= n_rows:
        raise ValueError("invalid final holdout boundary")
    return HoldoutSplit(tuple(range(cut)), tuple(range(cut, n_rows)))


def _as_xy(rows: Sequence, indices: Sequence[int]) -> tuple[list[list[float]], list[int]]:
    x = [list(rows[i].values) for i in indices]
    y = [1 if rows[i].target_return > 0.0 else 0 for i in indices]
    if not x:
        raise ValueError("empty model sample")
    return x, y


def fit_probability_model(rows: Sequence, indices: Sequence[int]) -> LogisticRegression:
    x, y = _as_xy(rows, indices)
    if len(set(y)) < 2:
        raise ValueError("training data contains only one target class")
    model = LogisticRegression(C=1.0, penalty="l2", solver="liblinear", random_state=0)
    model.fit(x, y)
    return model


def predict_rows(model: LogisticRegression, rows: Sequence, indices: Sequence[int]) -> list[Prediction]:
    if not indices:
        return []
    probabilities = model.predict_proba([list(rows[i].values) for i in indices])[:, 1]
    return [
        Prediction(
            index=i,
            timestamp=rows[i].timestamp,
            probability_up=float(probabilities[pos]),
            target_up=1 if rows[i].target_return > 0.0 else 0,
            target_return=float(rows[i].target_return),
        )
        for pos, i in enumerate(indices)
    ]


def brier_score(predictions: Sequence[Prediction]) -> float:
    if not predictions:
        raise ValueError("predictions must not be empty")
    return sum((p.probability_up - p.target_up) ** 2 for p in predictions) / len(predictions)


def log_loss(predictions: Sequence[Prediction]) -> float:
    if not predictions:
        raise ValueError("predictions must not be empty")
    total = 0.0
    eps = 1e-15
    for p in predictions:
        prob = min(max(p.probability_up, eps), 1.0 - eps)
        total += -(p.target_up * log(prob) + (1 - p.target_up) * log(1.0 - prob))
    return total / len(predictions)


def directional_accuracy(predictions: Sequence[Prediction], threshold: float = 0.5) -> float:
    if not predictions:
        raise ValueError("predictions must not be empty")
    correct = sum((p.probability_up >= threshold) == bool(p.target_up) for p in predictions)
    return correct / len(predictions)


def positive_rate(predictions: Sequence[Prediction]) -> float:
    if not predictions:
        raise ValueError("predictions must not be empty")
    return sum(p.target_up for p in predictions) / len(predictions)
