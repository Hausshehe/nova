from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.directional_failure_diagnostics import evaluate_directional_failure_diagnostics


def _bars(n: int = 80) -> list[Bar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(start + timedelta(days=i), 1.0, 1.0, 1.0, 1.0 + i * 0.0002, 1.0)
        for i in range(n)
    ]


def test_directional_failure_diagnostics_has_expected_sections() -> None:
    report = evaluate_directional_failure_diagnostics(_bars(), folds=4)
    assert report["candidate_bars"] >= 0
    assert "full_sample" in report
    assert len(report["chronological_folds"]) == 4
