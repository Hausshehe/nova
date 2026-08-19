from datetime import datetime, timezone

from trading_research.data import Bar
from trading_research.market_history import MarketHistoryStore
from trading_research.multitimeframe_context import MultiTimeframeContext, TimeframeWindow


def _bar(day: int, price: float) -> Bar:
    return Bar(
        timestamp=datetime(2026, 1, day, tzinfo=timezone.utc),
        open=price,
        high=price + 0.001,
        low=price - 0.001,
        close=price,
        volume=100,
    )


def test_build_returns_bounded_context(tmp_path):
    store = MarketHistoryStore(tmp_path / "market.sqlite3")
    try:
        store.append("EURUSD", "1D", _bar(1, 1.10))
        store.append("EURUSD", "1D", _bar(2, 1.11))
        store.append("EURUSD", "1H", _bar(1, 1.10))
        context = MultiTimeframeContext(
            store,
            windows=(TimeframeWindow("1H", 1), TimeframeWindow("1D", 2)),
        )
        payload = context.build("EURUSD", focus_timeframe="1H")
        assert '"focus_timeframe":"1H"' in payload
        assert payload.index('"timeframe":"1H"') < payload.index('"timeframe":"1D"')
        assert payload.count('"close"') == 3
    finally:
        store.close()


def test_invalid_window_is_rejected(tmp_path):
    store = MarketHistoryStore(tmp_path / "market.sqlite3")
    try:
        try:
            MultiTimeframeContext(store, windows=(TimeframeWindow("1D", 0),))
        except ValueError as exc:
            assert "limit must be positive" in str(exc)
        else:
            raise AssertionError("expected ValueError")
    finally:
        store.close()
