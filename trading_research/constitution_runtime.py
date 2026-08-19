"""Runtime enforcement bridge for Nova's trading constitution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from .trading_constitution import TradingConstitution


@dataclass(frozen=True)
class ConstitutionDecision:
    allowed: bool
    reason: str


def validate_demo_runtime(
    constitution: TradingConstitution,
    *,
    demo_mode: bool,
    daily_loss_fraction: float = 0.0,
    open_positions: int = 0,
    spread_bps: float | None = None,
    session_time: time | None = None,
) -> ConstitutionDecision:
    constitution.validate()

    if constitution.demo_only and not demo_mode:
        return ConstitutionDecision(False, "trading_constitution_requires_demo_mode")
    if constitution.require_kill_switch is False:
        return ConstitutionDecision(False, "trading_constitution_requires_kill_switch")
    if constitution.require_deterministic_policy is False:
        return ConstitutionDecision(False, "trading_constitution_requires_deterministic_policy")
    if constitution.require_structured_ai_decision is False:
        return ConstitutionDecision(False, "trading_constitution_requires_structured_ai_decision")
    if constitution.require_approved_strategy is False:
        return ConstitutionDecision(False, "trading_constitution_requires_approved_strategy_gate")
    if daily_loss_fraction >= constitution.max_daily_loss_fraction:
        return ConstitutionDecision(False, "trading_constitution_daily_loss_limit")
    if open_positions >= constitution.max_open_positions:
        return ConstitutionDecision(False, "trading_constitution_open_position_limit")
    if spread_bps is not None and spread_bps > constitution.max_spread_bps:
        return ConstitutionDecision(False, "trading_constitution_spread_limit")
    if session_time is not None and not (constitution.session_start <= session_time < constitution.session_end):
        return ConstitutionDecision(False, "trading_constitution_outside_session")
    return ConstitutionDecision(True, "trading_constitution_passed")
