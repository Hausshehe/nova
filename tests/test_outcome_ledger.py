from datetime import datetime, timedelta, timezone

import pytest

from trading_research.data import Bar
from trading_research.outcome_ledger import build_outcome_ledger


def _bars(closes: list[float]) -> list[Bar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [Bar(start + timedelta(days=i), close, close, close, close, 1.0) for i, close in enumerate(closes)]


def test_ledger_keeps_future_outcomes_as_labels_only():
    bars = _bars([1.0] * 60 + [1.01, 1.02, 1.04, 1.03, 1.0])
    records = build_outcome_ledger(bars)
    assert len(records) == len(bars)
    assert records[59].history_available is True
    assert records[59].terminal_close_return_bps == pytest.approx(300.0)
    assert records[59].max_abs_close_move_bps == pytest.approx(400.0)
    assert records[59].opportunity_label is True
    assert records[59].actionable_label is False
    assert records[-1].insufficient_future_window is True
    assert records[-1].max_abs_close_move_bps is not None


def test_ledger_rejects_invalid_parameters():
    bars = _bars([1.0] * 60)
    with pytest.raises(ValueError):
        build_outcome_ledger(bars, future_bars=0)
    with pytest.raises(ValueError):
        build_outcome_ledger(bars, slow_period=20, fast_period=20)
