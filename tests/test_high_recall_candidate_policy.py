from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.high_recall_candidate_policy import build_high_recall_candidates


def _bars(count: int = 60):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return tuple(
        Bar(
            timestamp=start + timedelta(minutes=i),
            open=1.0 + i * 0.001,
            high=1.001 + i * 0.001,
            low=0.999 + i * 0.001,
            close=1.0 + i * 0.001,
            volume=1.0,
        )
        for i in range(count)
    )


def test_empty_bars_return_no_candidates():
    assert build_high_recall_candidates(()) == ()


def test_one_candidate_record_per_bar():
    bars = _bars()
    candidates = build_high_recall_candidates(bars)
    assert len(candidates) == len(bars)
    assert [candidate.index for candidate in candidates] == list(range(len(bars)))
    assert all(isinstance(candidate.evidence, tuple) for candidate in candidates)
