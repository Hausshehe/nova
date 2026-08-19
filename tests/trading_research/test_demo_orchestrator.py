from datetime import datetime, timezone

from trading_research.adaptive_market_brain import AdaptiveMarketBrain, AdaptiveMarketResult
from trading_research.decision_policy import RiskSnapshot
from trading_research.demo_orchestrator import DemoTradingOrchestrator
from trading_research.demo_supervisor import DemoTradingSupervisor
from trading_research.execution import DemoExecutionGateway
from trading_research.market_monitor import MarketEvent
from trading_research.market_reasoner import MarketAnalysis
from trading_research.memory import ExperienceStore


NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


class FakeBrain:
    def __init__(self, analysis):
        self.analysis = analysis

    def process(self, event):
        return AdaptiveMarketResult(
            escalation=type("E", (), {"recommended_poll_seconds": 1})(),
            analysis=self.analysis,
        )


def _event():
    return MarketEvent(
        event_type="PRICE_MOVE",
        symbol="EURUSD",
        timeframe="15M",
        timestamp=NOW,
        reason="strategy setup",
        price=1.1,
        change_bps=55.0,
        spread_bps=2.0,
    )


def test_setup_does_not_execute_without_explicit_enter_action():
    analysis = MarketAnalysis(
        assessment="SETUP",
        rationale="setup requires further confirmation",
        relevant_strategies=("approved_v1",),
        urgency="ELEVATED",
    )
    store = ExperienceStore(":memory:")
    gateway = DemoExecutionGateway()
    orchestrator = DemoTradingOrchestrator(
        brain=FakeBrain(analysis),
        supervisor=DemoTradingSupervisor(now=lambda: NOW),
        experience=store,
        gateway=gateway,
        strategy_lookup=lambda *_: True,
        strategy_version_resolver=lambda *_: "1.0",
    )
    result = orchestrator.process_event(
        _event(),
        broker_connected=True,
        demo_mode=True,
        reconciled=True,
        risk=RiskSnapshot(0.0, 0, 2.0),
    )
    assert result.execution is None
    assert gateway.records == ()


def test_risk_exit_with_approved_strategy_and_known_position_direction_reaches_demo_gateway():
    analysis = MarketAnalysis(
        assessment="RISK",
        rationale="risk condition requires an exit",
        relevant_strategies=("approved_v1",),
        urgency="CRITICAL",
    )
    store = ExperienceStore(":memory:")
    gateway = DemoExecutionGateway()
    orchestrator = DemoTradingOrchestrator(
        brain=FakeBrain(analysis),
        supervisor=DemoTradingSupervisor(now=lambda: NOW),
        experience=store,
        gateway=gateway,
        strategy_lookup=lambda name, version: (name, version) == ("approved_v1", "1.0"),
        strategy_version_resolver=lambda *_: "1.0",
        position_direction_resolver=lambda _: "LONG",
    )
    result = orchestrator.process_event(
        _event(),
        broker_connected=True,
        demo_mode=True,
        reconciled=True,
        risk=RiskSnapshot(0.0, 0, 2.0),
    )
    assert result.execution is not None
    assert result.execution.accepted is True
    assert result.execution.environment == "DEMO"


def test_exit_is_rejected_when_position_direction_is_unknown():
    analysis = MarketAnalysis(
        assessment="RISK",
        rationale="risk condition requires an exit",
        relevant_strategies=("approved_v1",),
        urgency="CRITICAL",
    )
    gateway = DemoExecutionGateway()
    orchestrator = DemoTradingOrchestrator(
        brain=FakeBrain(analysis),
        supervisor=DemoTradingSupervisor(now=lambda: NOW),
        experience=ExperienceStore(":memory:"),
        gateway=gateway,
        strategy_lookup=lambda *_: True,
        strategy_version_resolver=lambda *_: "1.0",
        position_direction_resolver=lambda _: None,
    )
    result = orchestrator.process_event(
        _event(),
        broker_connected=True,
        demo_mode=True,
        reconciled=True,
    )
    assert result.policy_allowed is False
    assert result.policy_reason == "exit_position_direction_unresolved"
    assert gateway.records == ()


def test_unhealthy_supervisor_stops_before_brain_execution():
    analysis = MarketAnalysis(
        assessment="RISK",
        rationale="should not be reached",
        relevant_strategies=("approved_v1",),
        urgency="CRITICAL",
    )
    store = ExperienceStore(":memory:")
    gateway = DemoExecutionGateway()
    orchestrator = DemoTradingOrchestrator(
        brain=FakeBrain(analysis),
        supervisor=DemoTradingSupervisor(now=lambda: NOW),
        experience=store,
        gateway=gateway,
        strategy_lookup=lambda *_: True,
        strategy_version_resolver=lambda *_: "1.0",
        position_direction_resolver=lambda _: "LONG",
    )
    result = orchestrator.process_event(
        _event(),
        broker_connected=False,
        demo_mode=True,
        reconciled=True,
    )
    assert result.policy_allowed is False
    assert result.policy_reason == "supervisor_unhealthy"
    assert gateway.records == ()
