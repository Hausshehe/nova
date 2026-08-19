from datetime import datetime, timedelta, timezone

from trading_research.adaptive_market_brain import AdaptiveMarketBrain
from trading_research.data import Bar
from trading_research.demo_orchestrator import DemoTradingOrchestrator
from trading_research.demo_supervisor import DemoTradingSupervisor, SupervisorConfig
from trading_research.escalation import AdaptiveEscalator
from trading_research.execution import DemoExecutionGateway
from trading_research.market_monitor import MarketEvent
from trading_research.memory import ExperienceStore
from trading_research.market_reasoner import MarketAnalysis
from trading_research.decision_policy import RiskSnapshot
from trading_research.trade_safety import TradingKillSwitch


class EnterReasoner:
    def analyze(self, event, *, strategy_context="", market_context=""):
        return MarketAnalysis(
            assessment="RISK",
            rationale="Adversarial test recommendation.",
            relevant_strategies=("demo_strategy",),
            urgency="CRITICAL",
        )


def event():
    return MarketEvent(
        event_type="PRICE_MOVE",
        symbol="EURUSD",
        timeframe="1D",
        timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
        reason="test move",
        price=1.1,
        change_bps=50.0,
        spread_bps=1.0,
    )


def orchestrator(tmp_path, supervisor):
    brain = AdaptiveMarketBrain(AdaptiveEscalator(), EnterReasoner())
    return DemoTradingOrchestrator(
        brain=brain,
        supervisor=supervisor,
        experience=ExperienceStore(tmp_path / "experience.sqlite3"),
        gateway=DemoExecutionGateway(),
        strategy_lookup=lambda name, version: name == "demo_strategy" and version == "1.0",
        strategy_version_resolver=lambda name, _: "1.0" if name == "demo_strategy" else None,
    )


def test_disconnected_broker_fails_closed_before_ai_or_execution(tmp_path):
    supervisor = DemoTradingSupervisor(now=lambda: event().timestamp)
    result = orchestrator(tmp_path, supervisor).process_event(
        event(), broker_connected=False, demo_mode=True, reconciled=True,
        market_timestamp=event().timestamp, reference_time=event().timestamp,
    )
    assert result.policy_allowed is False
    assert result.policy_reason == "supervisor_unhealthy"
    assert result.execution is None
    assert supervisor.kill_switch.allow_execution() is False


def test_live_mode_fails_closed(tmp_path):
    supervisor = DemoTradingSupervisor(now=lambda: event().timestamp)
    result = orchestrator(tmp_path, supervisor).process_event(
        event(), broker_connected=True, demo_mode=False, reconciled=True,
        market_timestamp=event().timestamp, reference_time=event().timestamp,
    )
    assert result.execution is None
    assert result.policy_reason == "supervisor_unhealthy"


def test_unreconciled_account_fails_closed(tmp_path):
    supervisor = DemoTradingSupervisor(now=lambda: event().timestamp)
    result = orchestrator(tmp_path, supervisor).process_event(
        event(), broker_connected=True, demo_mode=True, reconciled=False,
        market_timestamp=event().timestamp, reference_time=event().timestamp,
    )
    assert result.execution is None
    assert result.policy_reason == "supervisor_unhealthy"


def test_future_market_timestamp_trips_kill_switch(tmp_path):
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    future = now + timedelta(seconds=1)
    supervisor = DemoTradingSupervisor(now=lambda: now)
    result = orchestrator(tmp_path, supervisor).process_event(
        event(), broker_connected=True, demo_mode=True, reconciled=True,
        market_timestamp=future, reference_time=now,
    )
    assert result.execution is None
    assert result.policy_reason == "supervisor_unhealthy"
    assert "market_data_timestamp_in_future" in supervisor.last_snapshot.reasons


def test_stale_market_data_trips_kill_switch(tmp_path):
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    stale = now - timedelta(seconds=31)
    supervisor = DemoTradingSupervisor(
        config=SupervisorConfig(max_market_data_age_seconds=30.0),
        now=lambda: now,
    )
    result = orchestrator(tmp_path, supervisor).process_event(
        event(), broker_connected=True, demo_mode=True, reconciled=True,
        market_timestamp=stale, reference_time=now,
    )
    assert result.execution is None
    assert result.policy_reason == "supervisor_unhealthy"
    assert any(reason.startswith("stale_market_data:") for reason in supervisor.last_snapshot.reasons)


def test_kill_switch_latches_after_failure(tmp_path):
    kill_switch = TradingKillSwitch()
    supervisor = DemoTradingSupervisor(kill_switch=kill_switch, now=lambda: event().timestamp)
    first = orchestrator(tmp_path, supervisor).process_event(
        event(), broker_connected=False, demo_mode=True, reconciled=True,
        market_timestamp=event().timestamp, reference_time=event().timestamp,
    )
    second = orchestrator(tmp_path, supervisor).process_event(
        event(), broker_connected=True, demo_mode=True, reconciled=True,
        market_timestamp=event().timestamp, reference_time=event().timestamp,
    )
    assert first.execution is None
    assert second.execution is None
    assert second.policy_reason == "supervisor_unhealthy"


def test_high_risk_snapshot_blocks_execution_even_when_supervisor_is_healthy(tmp_path):
    supervisor = DemoTradingSupervisor(now=lambda: event().timestamp)
    result = orchestrator(tmp_path, supervisor).process_event(
        event(), broker_connected=True, demo_mode=True, reconciled=True,
        market_timestamp=event().timestamp, reference_time=event().timestamp,
        risk=RiskSnapshot(daily_loss_fraction=0.10, open_positions=0, spread_bps=1.0),
    )
    assert result.execution is None
    assert result.policy_allowed is False
