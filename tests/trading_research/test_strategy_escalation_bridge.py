from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.market_monitor import MarketEvent
from trading_research.strategy_escalation_bridge import evaluate_strategy_escalation


def _bars(n=60):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        Bar(
            timestamp=base + timedelta(minutes=i),
            open=1.1000 + i * 0.00001,
            high=1.1010 + i * 0.00001,
            low=1.0990 + i * 0.00001,
            close=1.1000 + i * 0.00001,
            volume=100,
        )
        for i in range(n)
    )


def test_strategy_bridge_preserves_market_ai_requests():
    bars = _bars()
    event = MarketEvent(
        event_type="PRICE_MOVE",
        timestamp=bars[-1].timestamp,
        symbol="EURUSD",
        timeframe="M1",
        change_bps=25.0,
        spread_bps=2.0,
    )
    result = evaluate_strategy_escalation(bars, (event,))
    assert result[0].request_ai is True


def test_strategy_bridge_does_not_create_unbounded_duplicate_requests():
    bars = _bars()
    event1 = MarketEvent("PRICE_MOVE", bars[-1].timestamp, "EURUSD", "M1", 25.0, 2.0)
    event2 = MarketEvent("PRICE_MOVE", bars[-1].timestamp + timedelta(seconds=10), "EURUSD", "M1", 8.0, 2.0)
    result = evaluate_strategy_escalation(bars, (event1, event2), momentum_bps=1.0)
    assert result[0].request_ai is True
    assert result[1].request_ai is False
