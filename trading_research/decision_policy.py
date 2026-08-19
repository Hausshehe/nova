"""Deterministic policy checks between AI recommendations and execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .decision_contract import AIRecommendation


@dataclass(frozen=True)
class RiskSnapshot:
    daily_loss_fraction: float
    open_positions: int
    spread_bps: float | None = None


@dataclass(frozen=True)
class DecisionPolicy:
    max_daily_loss_fraction: float = 0.02
    max_open_positions: int = 3
    max_spread_bps: float = 25.0

    def validate(self) -> None:
        if self.max_daily_loss_fraction <= 0:
            raise ValueError("max_daily_loss_fraction must be positive")
        if self.max_open_positions < 0:
            raise ValueError("max_open_positions cannot be negative")
        if self.max_spread_bps <= 0:
            raise ValueError("max_spread_bps must be positive")


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def validate_recommendation(
    recommendation: AIRecommendation,
    *,
    approved_strategy_lookup: Callable[[str, str], bool],
    risk: RiskSnapshot,
    policy: DecisionPolicy | None = None,
) -> PolicyDecision:
    """Validate an AI recommendation without executing anything."""
    recommendation.validate()
    policy = policy or DecisionPolicy()
    policy.validate()

    if risk.daily_loss_fraction >= policy.max_daily_loss_fraction:
        return PolicyDecision(False, "daily_loss_limit_reached")
    if risk.open_positions > policy.max_open_positions:
        return PolicyDecision(False, "open_position_limit_reached")
    if risk.spread_bps is not None and risk.spread_bps > policy.max_spread_bps:
        return PolicyDecision(False, "spread_above_limit")

    if recommendation.action in {"ENTER", "EXIT"}:
        assert recommendation.strategy_name is not None
        assert recommendation.strategy_version is not None
        if not approved_strategy_lookup(
            recommendation.strategy_name, recommendation.strategy_version
        ):
            return PolicyDecision(False, "strategy_not_approved")

    return PolicyDecision(True, "deterministic_policy_passed")
