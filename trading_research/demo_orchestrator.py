"""End-to-end fail-closed orchestration for Nova's demo trading loop.

The orchestrator connects market events to optional AI reasoning, deterministic
policy, demo execution, and experience journaling. It has no live execution
path and refuses to proceed when supervisor health checks fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .adaptive_market_brain import AdaptiveMarketBrain
from .decision_contract import AIRecommendation, parse_recommendation
from .decision_policy import DecisionPolicy, RiskSnapshot, validate_recommendation
from .demo_supervisor import DemoTradingSupervisor
from .execution import DemoExecutionGateway, ExecutionRequest, ExecutionResult
from .market_monitor import MarketEvent
from .memory import ExperienceStore
from .trade_safety import TradeJournal


@dataclass(frozen=True)
class DemoCycleResult:
    event: MarketEvent
    recommendation: AIRecommendation | None
    policy_allowed: bool
    policy_reason: str
    execution: ExecutionResult | None


class DemoTradingOrchestrator:
    """Run one market event through Nova's complete demo-only decision path."""

    def __init__(
        self,
        *,
        brain: AdaptiveMarketBrain,
        supervisor: DemoTradingSupervisor,
        experience: ExperienceStore,
        strategy_lookup: Callable[[str, str], bool],
        strategy_version_resolver: Callable[[str, MarketEvent], str | None],
        gateway: DemoExecutionGateway | None = None,
        policy: DecisionPolicy | None = None,
        recommendation_parser: Callable[[str | dict], AIRecommendation] = parse_recommendation,
    ) -> None:
        self.brain = brain
        self.supervisor = supervisor
        self.experience = experience
        self.gateway = gateway or DemoExecutionGateway()
        self.strategy_lookup = strategy_lookup
        self.strategy_version_resolver = strategy_version_resolver
        self.policy = policy or DecisionPolicy()
        self.recommendation_parser = recommendation_parser
        self.journal = TradeJournal(experience)

    def process_event(
        self,
        event: MarketEvent,
        *,
        broker_connected: bool,
        demo_mode: bool,
        reconciled: bool,
        market_timestamp: datetime | None = None,
        reference_time: datetime | None = None,
        risk: RiskSnapshot | None = None,
        price: float | None = None,
        quantity: float = 1.0,
    ) -> DemoCycleResult:
        supervisor_snapshot = self.supervisor.check(
            market_timestamp=market_timestamp or event.timestamp,
            broker_connected=broker_connected,
            demo_mode=demo_mode,
            reconciled=reconciled,
            reference_time=reference_time,
        )
        if not supervisor_snapshot.healthy:
            return DemoCycleResult(event, None, False, "supervisor_unhealthy", None)

        brain_result = self.brain.process(event)
        if brain_result.analysis is None:
            return DemoCycleResult(event, None, False, "no_ai_escalation", None)

        analysis = brain_result.analysis
        action = {
            "NO_ACTION": "NO_ACTION",
            "WATCH": "WATCH",
            "SETUP": "WATCH",
            "RISK": "EXIT",
        }[analysis.assessment]
        strategy_name = analysis.relevant_strategies[0] if analysis.relevant_strategies else None
        strategy_version = (
            self.strategy_version_resolver(strategy_name, event)
            if strategy_name is not None and action in {"ENTER", "EXIT"}
            else None
        )
        if action in {"ENTER", "EXIT"} and (not strategy_name or not strategy_version):
            return DemoCycleResult(event, None, False, "strategy_identity_unresolved", None)

        recommendation_value = {
            "action": action,
            "strategy_name": strategy_name,
            "strategy_version": strategy_version,
            "rationale": analysis.rationale,
            "urgency": {"NORMAL": "LOW", "ELEVATED": "HIGH", "CRITICAL": "CRITICAL"}[analysis.urgency],
            "confidence": 0.5,
        }
        recommendation = self.recommendation_parser(recommendation_value)
        policy_risk = risk or RiskSnapshot(
            daily_loss_fraction=0.0,
            open_positions=0,
            spread_bps=event.spread_bps,
        )
        policy_decision = validate_recommendation(
            recommendation,
            approved_strategy_lookup=self.strategy_lookup,
            risk=policy_risk,
            policy=self.policy,
        )
        if not policy_decision.allowed:
            return DemoCycleResult(event, recommendation, False, policy_decision.reason, None)

        if recommendation.action not in {"ENTER", "EXIT"}:
            return DemoCycleResult(event, recommendation, True, policy_decision.reason, None)

        request = ExecutionRequest(
            recommendation=recommendation,
            symbol=event.symbol,
            timeframe=event.timeframe,
            price=price or event.price,
            quantity=quantity,
            timestamp_utc=event.timestamp.astimezone(timezone.utc),
        )
        execution = self.gateway.execute(request)
        self.journal.record_execution(
            request,
            execution,
            timeframe=event.timeframe,
            direction="LONG" if recommendation.action == "ENTER" else "SHORT",
            market_state={"event_type": event.event_type, "change_bps": event.change_bps},
        )
        return DemoCycleResult(event, recommendation, True, policy_decision.reason, execution)
