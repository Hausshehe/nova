"""Execution boundary for Nova's trading decisions.

The first implementation is deliberately demo-only and in-memory. It gives the
research/decision stack a real execution contract without granting the phone
or the LLM access to real MT5 trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .decision_contract import AIRecommendation
from .decision_policy import PolicyDecision, RiskSnapshot


@dataclass(frozen=True)
class ExecutionRequest:
    recommendation: AIRecommendation
    symbol: str
    timeframe: str
    price: float
    quantity: float
    timestamp_utc: datetime

    def validate(self) -> None:
        self.recommendation.validate()
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if not self.timeframe.strip() or self.timeframe.upper() == "UNKNOWN":
            raise ValueError("timeframe is required and cannot be UNKNOWN")
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("timestamp_utc must be timezone-aware")


@dataclass(frozen=True)
class ExecutionResult:
    accepted: bool
    execution_id: str
    message: str
    environment: str


class ExecutionGateway(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...


class DemoExecutionGateway:
    """Safe in-memory demo executor; it never talks to MT5 or a broker."""

    environment = "DEMO"

    def __init__(self) -> None:
        self._counter = 0
        self._records: list[ExecutionRequest] = []

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        request.validate()
        if request.recommendation.action not in {"ENTER", "EXIT"}:
            return ExecutionResult(
                accepted=False,
                execution_id="",
                message="execution requires ENTER or EXIT",
                environment=self.environment,
            )
        self._counter += 1
        execution_id = f"DEMO-{self._counter:06d}"
        self._records.append(request)
        return ExecutionResult(
            accepted=True,
            execution_id=execution_id,
            message="demo execution recorded; no external order was sent",
            environment=self.environment,
        )

    @property
    def records(self) -> tuple[ExecutionRequest, ...]:
        return tuple(self._records)


class DecisionExecutor:
    """Apply deterministic policy before handing an approved decision to a gateway."""

    def __init__(self, gateway: ExecutionGateway):
        self.gateway = gateway

    def execute_if_allowed(
        self,
        recommendation: AIRecommendation,
        *,
        symbol: str,
        timeframe: str,
        price: float,
        quantity: float,
        timestamp_utc: datetime | None,
        approved_strategy_lookup,
        risk: RiskSnapshot,
        policy=None,
    ) -> tuple[PolicyDecision, ExecutionResult | None]:
        from .decision_policy import validate_recommendation

        decision = validate_recommendation(
            recommendation,
            approved_strategy_lookup=approved_strategy_lookup,
            risk=risk,
            policy=policy,
        )
        if not decision.allowed:
            return decision, None

        request = ExecutionRequest(
            recommendation=recommendation,
            symbol=symbol,
            timeframe=timeframe,
            price=price,
            quantity=quantity,
            timestamp_utc=timestamp_utc or datetime.now(timezone.utc),
        )
        return decision, self.gateway.execute(request)
