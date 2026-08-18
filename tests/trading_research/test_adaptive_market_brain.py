from datetime import datetime, timezone

from trading_research.adaptive_market_brain import (
    AdaptiveMarketBrain,
    strategy_context_from_records,
)
from trading_research.escalation import AdaptiveEscalator, EscalationThresholds
from trading_research.market_monitor import MarketEvent
from trading_research.market_reasoner import MarketAnalysis


class FakeReasoner:
    def __init__(self):
        self.calls = []

    def analyze(self, event, *, strategy_context="", market_context=""):
        self.calls.append((event, strategy_context, market_context))
        return MarketAnalysis(
            assessment="WATCH",
            rationale="Escalated event requires inspection.",
            relevant_strategies=("approved_v1",),
            urgency="ELEVATED",
        )


def _event(move=55.0):
    return MarketEvent(
        event_type="PRICE_MOVE",
        symbol="EURUSD",
        timeframe="1D",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        reason="large move",
        price=1.1,
        change_bps=move,
        spread_bps=2.0,
    )


def test_brain_does_not_call_ai_for_routine_event():
    fake = FakeReasoner()
    brain = AdaptiveMarketBrain(AdaptiveEscalator(), fake)
    result = brain.process(_event(move=5.0))
    assert result.analysis is None
    assert fake.calls == []


def test_brain_calls_ai_for_critical_event():
    fake = FakeReasoner()
    brain = AdaptiveMarketBrain(AdaptiveEscalator(), fake)
    result = brain.process(_event())
    assert result.analysis is not None
    assert len(fake.calls) == 1


def test_strategy_context_filters_to_approved_matching_strategies():
    records = [
        {
            "strategy_name": "approved_v1",
            "strategy_version": "1.0",
            "status": "APPROVED",
            "hypothesis": {"symbol": "EURUSD", "timeframe": "1D", "rules": {"entry": "x"}},
        },
        {
            "strategy_name": "candidate_v1",
            "strategy_version": "1.0",
            "status": "CANDIDATE",
            "hypothesis": {"symbol": "EURUSD", "timeframe": "1D", "rules": {"entry": "y"}},
        },
        {
            "strategy_name": "other_symbol",
            "strategy_version": "1.0",
            "status": "APPROVED",
            "hypothesis": {"symbol": "GBPUSD", "timeframe": "1D", "rules": {"entry": "z"}},
        },
    ]
    context = strategy_context_from_records(records, symbol="EURUSD", timeframe="1D")
    assert "approved_v1:1.0" in context
    assert "candidate_v1" not in context
    assert "other_symbol" not in context
