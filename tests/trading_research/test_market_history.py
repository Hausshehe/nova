from datetime import datetime, timezone, timedelta

import pytest

from trading_research.data import Bar
from trading_research.market_history import MarketHistoryStore


def _bar(ts: int, close: float) -> Bar:
    when = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=ts)
    return Bar(when, close - 0.5, close + 1.0, close - 1.0, close, 100.0)


def test_append_and_recent_round_trip(tmp_path):
    store = MarketHistoryStore(tmp_path / "market.sqlite3")
    try:
        store.append_many("eurusd", "15m", [_bar(0, 100.0), _bar(1, 101.0), _bar(2, 102.0)])
        recent = store.recent("EURUSD", "15M", limit=2)
        assert [bar.close for bar in recent] == [101.0, 102.0]
    finally:
        store.close()


def test_duplicate_timestamp_is_replaced(tmp_path):
    store = MarketHistoryStore(tmp_path / "market.sqlite3")
    try:
        store.append("EURUSD", "15M", _bar(1, 101.0))
        store.append("EURUSD", "15M", _bar(1, 103.0))
        assert store.recent("EURUSD", "15M", 10)[0].close == 103.0
    finally:
        store.close()


def test_between_requires_timezone_aware_range(tmp_path):
    store = MarketHistoryStore(tmp_path / "market.sqlite3")
    try:
        with pytest.raises(ValueError, match="timezone-aware"):
            store.between("EURUSD", "15M", datetime(2026, 1, 1), datetime(2026, 1, 2))
    finally:
        store.close()


def test_compact_context_is_json_and_bounded(tmp_path):
    store = MarketHistoryStore(tmp_path / "market.sqlite3")
    try:
        store.append_many("EURUSD", "1H", [_bar(i, 100.0 + i) for i in range(5)])
        context = store.compact_context("EURUSD", "1H", limit=3)
        assert '"symbol":"EURUSD"' in context
        assert context.count('"close":') == 3
    finally:
        store.close()
