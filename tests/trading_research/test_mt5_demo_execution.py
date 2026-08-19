from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from trading_research.decision_contract import AIRecommendation
from trading_research.execution import ExecutionRequest
from trading_research.mt5_demo_execution import DemoExecutionUnavailable, MT5DemoExecutionGateway


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self, demo=True, order_retcode=10009):
        self.demo = demo
        self.order_retcode = order_retcode
        self.shutdown_called = False
        self.sent = []

    def initialize(self, *args, **kwargs):
        return True

    def shutdown(self):
        self.shutdown_called = True

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO if self.demo else 0)

    def symbol_select(self, symbol, enabled):
        return True

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(ask=1.1010, bid=1.1008)

    def order_check(self, order):
        return SimpleNamespace(retcode=0)

    def order_send(self, order):
        self.sent.append(order)
        return SimpleNamespace(retcode=self.order_retcode, order=123456)

    def last_error(self):
        return (0, "ok")


def _request():
    recommendation = AIRecommendation(
        action="ENTER",
        strategy_name="approved_v1",
        strategy_version="1.0",
        rationale="validated setup",
        urgency="HIGH",
        confidence=0.8,
    )
    return ExecutionRequest(
        recommendation=recommendation,
        symbol="EURUSD",
        timeframe="1D",
        price=1.10,
        quantity=0.01,
        timestamp_utc=datetime.now(timezone.utc),
    )


def test_gateway_refuses_non_demo_account():
    fake = FakeMT5(demo=False)
    gateway = MT5DemoExecutionGateway(module=fake)
    with pytest.raises(DemoExecutionUnavailable, match="not explicitly in DEMO"):
        gateway.connect()
    assert fake.shutdown_called is True


def test_gateway_requires_connection_before_execution():
    gateway = MT5DemoExecutionGateway(module=FakeMT5())
    with pytest.raises(DemoExecutionUnavailable, match="not connected"):
        gateway.execute(_request())


def test_gateway_executes_only_after_demo_guard_and_order_check():
    fake = FakeMT5(demo=True)
    gateway = MT5DemoExecutionGateway(module=fake)
    gateway.connect()
    result = gateway.execute(_request())
    assert result.accepted is True
    assert result.environment == "MT5_DEMO"
    assert fake.sent


def test_gateway_reports_order_rejection():
    fake = FakeMT5(demo=True, order_retcode=10013)
    gateway = MT5DemoExecutionGateway(module=fake)
    gateway.connect()
    result = gateway.execute(_request())
    assert result.accepted is False
    assert result.environment == "MT5_DEMO"
