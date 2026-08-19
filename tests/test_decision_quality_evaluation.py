from __future__ import annotations

from datetime import datetime, timezone

from trading_research.data import Bar
from tools.run_decision_quality_evaluation import _outcome_for_index


def _bar(i: int, close: float) -> Bar:
    return Bar(
        timestamp=datetime(2024, 1, 1 + i, tzinfo=timezone.utc),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
    )


def test_future_window_boundary_is_incomplete():
    bars = [_bar(i, 100.0) for i in range(4)]
    assert _outcome_for_index(bars, 0) is None


def test_actionable_label_uses_cost_buffer():
    bars = [_bar(0, 100.0), _bar(1, 100.30), _bar(2, 100.30), _bar(3, 100.30), _bar(4, 100.30)]
    outcome = _outcome_for_index(bars, 0)
    assert outcome is not None
    assert outcome["opportunity"] is True
    assert outcome["actionable"] is False


def test_actionable_label_clears_cost_buffer():
    bars = [_bar(0, 100.0), _bar(1, 100.35), _bar(2, 100.35), _bar(3, 100.35), _bar(4, 100.35)]
    outcome = _outcome_for_index(bars, 0)
    assert outcome is not None
    assert outcome["actionable"] is True
