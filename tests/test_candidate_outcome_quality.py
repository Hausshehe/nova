from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_research.candidate_outcome_quality import evaluate_candidate_outcome_quality
from trading_research.data import Bar


def _bars(n: int = 120) -> list[Bar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(start + timedelta(days=i), 1.0, 1.0, 1.0, 1.0 + i * 0.0001, 1.0)
        for i in range(n)
    ]


def test_quality_report_is_bounded_and_has_folds() -> None:
    full, folds = evaluate_candidate_outcome_quality(_bars(), folds=4)
    assert full.candidate_bars >= 0
    assert len(folds) == 4


def test_quality_report_is_empty_for_empty_dataset() -> None:
    full, folds = evaluate_candidate_outcome_quality([], folds=4)
    assert full.candidate_bars == 0
    assert full.complete_candidate_bars == 0
    assert len(folds) == 4
