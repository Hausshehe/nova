from datetime import datetime, timezone

import pytest

from trading_research.decision_contract import AIRecommendation
from trading_research.execution import DemoExecutionGateway, ExecutionRequest
from trading_research.memory import ExperienceStore
from trading_research.trade_safety import TradeJournal, TradingKillSwitch


def _request(action="ENTER"):
    return ExecutionRequest(
        recommendation=AIRecommendation(
            action=action,
            strategy_name="demo_strategy",
            strategy_version="1.0",
            rationale="validated demo decision",
            urgency="MEDIUM" if action == "ENTER" else "LOW",
            confidence=0.8,
        ),
        symbol="EURUSD",
        price=1.1,
        quantity=1000,
        timestamp_utc=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )


def test_kill_switch_fails_closed_until_reset():
    switch = TradingKillSwitch()
    assert switch.allow_execution() is True
    switch.trip("data integrity failure")
    assert switch.allow_execution() is False
    with pytest.raises(RuntimeError, match="data integrity failure"):
        switch.require_clear()
    switch.reset()
    assert switch.allow_execution() is True


def test_kill_switch_rejects_empty_reason():
    switch = TradingKillSwitch()
    with pytest.raises(ValueError, match="reason"):
        switch.trip("  ")


def test_trade_journal_records_explicit_direction_and_timeframe(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    gateway = DemoExecutionGateway()
    request = _request()
    result = gateway.execute(request)

    trade = TradeJournal(store).record_execution(
        request,
        result,
        timeframe="15M",
        direction="LONG",
        market_state={"volatility": "normal"},
    )

    assert trade is not None
    assert trade.direction == "LONG"
    assert trade.timeframe == "15M"
    stored = store.list_strategy_trades("demo_strategy", "1.0")
    assert len(stored) == 1
    assert stored[0].trade_id == result.execution_id


def test_trade_journal_rejects_invalid_direction(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    gateway = DemoExecutionGateway()
    request = _request()
    result = gateway.execute(request)

    with pytest.raises(ValueError, match="direction"):
        TradeJournal(store).record_execution(
            request,
            result,
            timeframe="15M",
            direction="EXIT",
        )
