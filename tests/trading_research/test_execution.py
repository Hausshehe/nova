from datetime import datetime, timezone

import pytest

from trading_research.decision_contract import AIRecommendation
from trading_research.decision_policy import RiskSnapshot
from trading_research.execution import DecisionExecutor, DemoExecutionGateway, ExecutionRequest


def _recommendation(action="ENTER"):
    return AIRecommendation(
        action=action,
        strategy_name="approved_v1" if action in {"ENTER", "EXIT"} else None,
        strategy_version="1.0" if action in {"ENTER", "EXIT"} else None,
        rationale="validated setup",
        urgency="HIGH",
        confidence=0.8,
    )


def _approved(name, version):
    return name == "approved_v1" and version == "1.0"


def test_demo_gateway_records_without_external_order():
    gateway = DemoExecutionGateway()
    result = gateway.execute(
        ExecutionRequest(
            recommendation=_recommendation(),
            symbol="EURUSD",
            timeframe="1D",
            price=1.10,
            quantity=1.0,
            timestamp_utc=datetime.now(timezone.utc),
        )
    )
    assert result.accepted is True
    assert result.environment == "DEMO"
    assert result.execution_id == "DEMO-000001"
    assert len(gateway.records) == 1


def test_executor_rejects_unapproved_strategy_without_execution():
    gateway = DemoExecutionGateway()
    executor = DecisionExecutor(gateway)
    decision, execution = executor.execute_if_allowed(
        _recommendation(),
        symbol="EURUSD",
        timeframe="1D",
        price=1.10,
        quantity=1.0,
        timestamp_utc=None,
        approved_strategy_lookup=lambda *_: False,
        risk=RiskSnapshot(daily_loss_fraction=0.0, open_positions=0, spread_bps=1.0),
    )
    assert decision.allowed is False
    assert decision.reason == "strategy_not_approved"
    assert execution is None
    assert gateway.records == ()


def test_executor_rejects_when_daily_loss_limit_is_reached():
    gateway = DemoExecutionGateway()
    executor = DecisionExecutor(gateway)
    decision, execution = executor.execute_if_allowed(
        _recommendation(),
        symbol="EURUSD",
        timeframe="1D",
        price=1.10,
        quantity=1.0,
        timestamp_utc=None,
        approved_strategy_lookup=_approved,
        risk=RiskSnapshot(daily_loss_fraction=0.02, open_positions=0, spread_bps=1.0),
    )
    assert decision.allowed is False
    assert decision.reason == "daily_loss_limit_reached"
    assert execution is None


def test_demo_gateway_rejects_non_order_action():
    gateway = DemoExecutionGateway()
    result = gateway.execute(
        ExecutionRequest(
            recommendation=_recommendation(action="WATCH"),
            symbol="EURUSD",
            timeframe="1D",
            price=1.10,
            quantity=1.0,
            timestamp_utc=datetime.now(timezone.utc),
        )
    )
    assert result.accepted is False
    assert gateway.records == ()


def test_request_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        ExecutionRequest(
            recommendation=_recommendation(),
            symbol="EURUSD",
            timeframe="1D",
            price=1.10,
            quantity=1.0,
            timestamp_utc=datetime.now(),
        ).validate()
