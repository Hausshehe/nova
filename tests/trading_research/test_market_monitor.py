from datetime import datetime, timezone

import pytest

from trading_research.data import Bar
from trading_research.market_monitor import EventThresholds, MarketMonitor, MarketSnapshot


def _bar(ts: int, close: float) -> Bar:
    timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
    return Bar(
        timestamp=timestamp,
        open=close,
        high=close + 0.0005,
        low=close - 0.0005,
        close=close,
        volume=100.0,
    )


def test_first_observation_emits_new_bar_only():
    monitor = MarketMonitor(EventThresholds(price_move_bps=20.0, spread_change_bps=10.0))
    events = monitor.observe(MarketSnapshot("EURUSD", "1D", _bar(1, 1.1000), spread_bps=5.0))
    assert [event.event_type for event in events] == ["NEW_BAR"]


def test_large_move_emits_price_event_and_new_bar():
    monitor = MarketMonitor(EventThresholds(price_move_bps=20.0))
    monitor.observe(MarketSnapshot("EURUSD", "1D", _bar(1, 1.1000)))
    events = monitor.observe(MarketSnapshot("EURUSD", "1D", _bar(2, 1.1030)))
    assert [event.event_type for event in events] == ["PRICE_MOVE", "NEW_BAR"]
    assert events[0].change_bps > 20.0


def test_spread_change_emits_event():
    monitor = MarketMonitor(EventThresholds(spread_change_bps=3.0))
    monitor.observe(MarketSnapshot("EURUSD", "1D", _bar(1, 1.1000), spread_bps=5.0))
    events = monitor.observe(MarketSnapshot("EURUSD", "1D", _bar(2, 1.1001), spread_bps=9.0))
    assert any(event.event_type == "SPREAD_CHANGE" for event in events)


def test_same_bar_is_ignored_by_default():
    monitor = MarketMonitor()
    snapshot = MarketSnapshot("EURUSD", "1D", _bar(1, 1.1000))
    assert monitor.observe(snapshot)[0].event_type == "NEW_BAR"
    assert monitor.observe(snapshot) == ()


def test_negative_threshold_is_rejected():
    with pytest.raises(ValueError, match="price_move_bps"):
        MarketMonitor(EventThresholds(price_move_bps=0.0))


def test_history_replay_is_deterministic():
    bars = [_bar(1, 1.1000), _bar(2, 1.1001), _bar(3, 1.1035)]
    monitor = MarketMonitor(EventThresholds(price_move_bps=20.0))
    events = monitor.observe_history("EURUSD", "1D", bars)
    assert [event.event_type for event in events] == ["NEW_BAR", "NEW_BAR", "PRICE_MOVE", "NEW_BAR"]


def test_history_spread_length_must_match():
    with pytest.raises(ValueError, match="spreads_bps"):
        MarketMonitor().observe_history(
            "EURUSD", "1D", [_bar(1, 1.1000)], spreads_bps=[]
        )
