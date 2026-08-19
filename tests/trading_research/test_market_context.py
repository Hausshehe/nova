from datetime import datetime, timezone

from trading_research.data import Bar
from trading_research.market_context import MarketHistoryRecorder
from trading_research.market_history import MarketHistoryStore
from trading_research.market_monitor import MarketSnapshot


def test_recorder_persists_snapshot_and_returns_compact_context(tmp_path):
    store = MarketHistoryStore(tmp_path / "market.sqlite3")
    try:
        recorder = MarketHistoryRecorder(store)
        bar = Bar(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            100.0, 102.0, 99.0, 101.0, 50.0,
        )
        recorder.record(MarketSnapshot("EURUSD", "15M", bar))
        context = recorder.context("EURUSD", "15M", limit=10)
        assert '"symbol":"EURUSD"' in context
        assert '"close":101.0' in context
    finally:
        store.close()
