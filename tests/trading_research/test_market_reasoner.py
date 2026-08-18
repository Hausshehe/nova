import json
from datetime import datetime, timezone

import pytest

from trading_research.market_monitor import MarketEvent
from trading_research.market_reasoner import GroqMarketReasoner, MarketAnalysis


def _event():
    return MarketEvent(
        event_type="PRICE_MOVE",
        symbol="EURUSD",
        timeframe="1D",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        reason="large price move",
        price=1.1,
        change_bps=55.0,
        spread_bps=3.0,
    )


def _response(data):
    return {"choices": [{"message": {"content": json.dumps(data)}}]}


def test_market_analysis_validation():
    analysis = MarketAnalysis(
        assessment="SETUP",
        rationale="An approved strategy may be relevant.",
        relevant_strategies=("breakout_v1",),
        urgency="ELEVATED",
    )
    analysis.validate()


def test_reasoner_returns_structured_analysis_without_execution_fields():
    calls = []

    def transport(payload):
        calls.append(payload)
        return _response(
            {
                "assessment": "WATCH",
                "rationale": "The move warrants inspection.",
                "relevant_strategies": ["breakout_v1"],
                "urgency": "ELEVATED",
            }
        )

    reasoner = GroqMarketReasoner("test-key", transport=transport)
    result = reasoner.analyze(_event())

    assert result.assessment == "WATCH"
    assert result.relevant_strategies == ("breakout_v1",)
    assert "order_send" not in calls[0]["messages"][0]["content"]
    assert "position size" in calls[0]["messages"][0]["content"]


def test_reasoner_rejects_invalid_model_assessment():
    def transport(_):
        return _response(
            {
                "assessment": "BUY",
                "rationale": "buy now",
                "relevant_strategies": [],
                "urgency": "CRITICAL",
            }
        )

    reasoner = GroqMarketReasoner("test-key", transport=transport)
    with pytest.raises(ValueError, match="unsupported assessment"):
        reasoner.analyze(_event())
