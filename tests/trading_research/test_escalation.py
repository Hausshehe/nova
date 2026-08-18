from datetime import datetime, timezone

import pytest

from trading_research.escalation import AdaptiveEscalator, EscalationThresholds
from trading_research.market_monitor import MarketEvent


def event(event_type: str, *, move: float | None = None, spread: float | None = None, second: int = 0):
    return MarketEvent(
        event_type=event_type,
        symbol="EURUSD",
        timeframe="1M",
        timestamp=datetime(2026, 1, 1, 12, 0, second, tzinfo=timezone.utc),
        reason="test",
        price=1.10,
        change_bps=move,
        spread_bps=spread,
    )


def test_new_bar_stays_routine():
    decision = AdaptiveEscalator().evaluate(event("NEW_BAR"))
    assert decision.level == "ROUTINE"
    assert decision.request_ai is False
    assert decision.recommended_poll_seconds == 15


def test_meaningful_price_move_requests_ai():
    decision = AdaptiveEscalator().evaluate(event("PRICE_MOVE", move=25.0))
    assert decision.level == "ELEVATED"
    assert decision.request_ai is True
    assert decision.recommended_poll_seconds == 5


def test_large_price_move_is_critical():
    decision = AdaptiveEscalator().evaluate(event("PRICE_MOVE", move=60.0))
    assert decision.level == "CRITICAL"
    assert decision.request_ai is True
    assert decision.recommended_poll_seconds == 1


def test_ai_cooldown_prevents_token_storm():
    escalator = AdaptiveEscalator(EscalationThresholds(ai_cooldown_seconds=60))
    first = escalator.evaluate(event("PRICE_MOVE", move=25.0, second=0))
    second = escalator.evaluate(event("PRICE_MOVE", move=30.0, second=10))
    assert first.request_ai is True
    assert second.request_ai is False
    assert "cooldown" in second.reason


def test_cooldown_expires():
    escalator = AdaptiveEscalator(EscalationThresholds(ai_cooldown_seconds=60))
    first = escalator.evaluate(event("PRICE_MOVE", move=25.0, second=0))
    second = escalator.evaluate(event("PRICE_MOVE", move=30.0, second=59))
    third = escalator.evaluate(event("PRICE_MOVE", move=30.0, second=60))
    assert first.request_ai is True
    assert second.request_ai is False
    assert third.request_ai is True


def test_invalid_thresholds_are_rejected():
    with pytest.raises(ValueError):
        EscalationThresholds(critical_move_bps=10, elevated_move_bps=20).validate()
