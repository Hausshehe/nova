from datetime import datetime, timezone

from trading_research.constitution_runtime import validate_demo_runtime
from trading_research.escalation import AdaptiveEscalator
from trading_research.market_monitor import MarketEvent
from trading_research.trading_constitution import TradingConstitution


def test_constitution_keeps_demo_runtime_inside_session():
    constitution = TradingConstitution()
    event = MarketEvent(
        event_type="PRICE_MOVE",
        symbol="EURUSD",
        timeframe="1D",
        timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        reason="move",
        price=1.1,
        change_bps=30.0,
    )
    decision = validate_demo_runtime(
        constitution,
        demo_mode=True,
        session_time=event.timestamp.time(),
    )
    assert decision.allowed is True


def test_constitution_blocks_outside_session():
    constitution = TradingConstitution()
    decision = validate_demo_runtime(
        constitution,
        demo_mode=True,
        session_time=constitution.session_end,
    )
    assert decision.allowed is False
    assert decision.reason == "trading_constitution_outside_session"


def test_escalator_remains_deterministic_under_constitution():
    event = MarketEvent(
        event_type="PRICE_MOVE",
        symbol="EURUSD",
        timeframe="1D",
        timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        reason="large move",
        price=1.1,
        change_bps=50.0,
    )
    first = AdaptiveEscalator().evaluate(event)
    second = AdaptiveEscalator().evaluate(event)
    assert first == second
