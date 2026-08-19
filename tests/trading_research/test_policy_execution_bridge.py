from datetime import datetime, timezone

from trading_research.adaptive_market_brain import AdaptiveMarketBrain
from trading_research.decision_contract import AIRecommendation
from trading_research.decision_policy import DecisionPolicy, RiskSnapshot, validate_recommendation


def _recommendation():
    return AIRecommendation(
        action="ENTER",
        strategy_name="approved_v1",
        strategy_version="1.0",
        rationale="setup aligns with approved strategy",
        urgency="HIGH",
        confidence=0.9,
    )


def test_policy_rejects_position_limit_at_boundary():
    decision = validate_recommendation(
        _recommendation(),
        approved_strategy_lookup=lambda *_: True,
        risk=RiskSnapshot(daily_loss_fraction=0.0, open_positions=3, spread_bps=1.0),
        policy=DecisionPolicy(max_open_positions=3),
    )
    assert decision.allowed is False
    assert decision.reason == "open_position_limit_reached"


def test_policy_allows_valid_demo_candidate():
    decision = validate_recommendation(
        _recommendation(),
        approved_strategy_lookup=lambda name, version: (name, version) == ("approved_v1", "1.0"),
        risk=RiskSnapshot(daily_loss_fraction=0.0, open_positions=0, spread_bps=1.0),
    )
    assert decision.allowed is True


def test_brain_can_route_recommendation_to_policy():
    class FakeReasoner:
        def analyze(self, event, *, strategy_context="", market_context=""):
            from trading_research.market_reasoner import MarketAnalysis
            return MarketAnalysis(
                assessment="SETUP",
                rationale="approved setup",
                relevant_strategies=("approved_v1",),
                urgency="ELEVATED",
                recommendation=_recommendation(),
            )

    from trading_research.escalation import AdaptiveEscalator
    from trading_research.market_monitor import MarketEvent

    event = MarketEvent(
        event_type="PRICE_MOVE",
        symbol="EURUSD",
        timeframe="1D",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        reason="large move",
        price=1.10,
        change_bps=55.0,
        spread_bps=2.0,
    )
    brain = AdaptiveMarketBrain(
        AdaptiveEscalator(),
        FakeReasoner(),
        recommendation_policy=lambda recommendation: validate_recommendation(
            recommendation,
            approved_strategy_lookup=lambda *_: True,
            risk=RiskSnapshot(daily_loss_fraction=0.0, open_positions=0, spread_bps=2.0),
        ),
    )
    result = brain.process(event)
    assert result.analysis is not None
    assert result.policy_decision is not None
    assert result.policy_decision.allowed is True
