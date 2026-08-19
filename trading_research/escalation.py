"""Deterministic adaptive escalation for market monitoring.

This layer sits between the cheap Python market monitor and an optional AI
reasoning provider. It decides when an ordinary observation deserves richer
inspection. It never calls an LLM and never executes trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Hashable

from .market_monitor import MarketEvent


@dataclass(frozen=True)
class EscalationThresholds:
    """Rules controlling how aggressively observations reach an AI layer."""

    elevated_move_bps: float = 20.0
    critical_move_bps: float = 50.0
    elevated_spread_bps: float = 10.0
    critical_spread_bps: float = 25.0
    ai_cooldown_seconds: int = 60
    min_state_change_bps: float = 12.0

    def validate(self) -> None:
        if self.elevated_move_bps <= 0:
            raise ValueError("elevated_move_bps must be positive")
        if self.critical_move_bps < self.elevated_move_bps:
            raise ValueError("critical_move_bps must be >= elevated_move_bps")
        if self.elevated_spread_bps <= 0:
            raise ValueError("elevated_spread_bps must be positive")
        if self.critical_spread_bps < self.elevated_spread_bps:
            raise ValueError("critical_spread_bps must be >= elevated_spread_bps")
        if self.ai_cooldown_seconds < 0:
            raise ValueError("ai_cooldown_seconds cannot be negative")
        if self.min_state_change_bps <= 0:
            raise ValueError("min_state_change_bps must be positive")


@dataclass(frozen=True)
class EscalationDecision:
    level: str
    request_ai: bool
    reason: str
    recommended_poll_seconds: int


class AdaptiveEscalator:
    """Convert market events into bounded AI-escalation decisions."""

    def __init__(self, thresholds: EscalationThresholds | None = None):
        self.thresholds = thresholds or EscalationThresholds()
        self.thresholds.validate()
        self._last_ai_request: dict[tuple[str, str], datetime] = {}
        self._last_ai_state: dict[tuple[str, str], float] = {}

    def evaluate(self, event: MarketEvent, *, state_value_bps: float | None = None) -> EscalationDecision:
        move = event.change_bps or 0.0
        spread = event.spread_bps or 0.0

        if event.event_type == "PRICE_MOVE" and move >= self.thresholds.critical_move_bps:
            level = "CRITICAL"
            reason = f"large price move: {move:.2f} bps"
            poll = 1
        elif event.event_type == "SPREAD_CHANGE" and spread >= self.thresholds.critical_spread_bps:
            level = "CRITICAL"
            reason = f"wide spread condition: {spread:.2f} bps"
            poll = 1
        elif event.event_type == "PRICE_MOVE" and move >= self.thresholds.elevated_move_bps:
            level = "ELEVATED"
            reason = f"meaningful price move: {move:.2f} bps"
            poll = 5
        elif event.event_type == "SPREAD_CHANGE" and spread >= self.thresholds.elevated_spread_bps:
            level = "ELEVATED"
            reason = f"meaningful spread condition: {spread:.2f} bps"
            poll = 5
        elif event.event_type == "NEW_BAR":
            level = "ROUTINE"
            reason = "new bar observed; keep monitoring cheaply"
            poll = 15
        else:
            level = "ROUTINE"
            reason = "ordinary market observation"
            poll = 15

        request_ai = False
        if level in {"ELEVATED", "CRITICAL"}:
            request_ai = self._cooldown_allows(event, state_value_bps)
            if not request_ai:
                reason += "; AI cooldown active"

        return EscalationDecision(
            level=level,
            request_ai=request_ai,
            reason=reason,
            recommended_poll_seconds=poll,
        )

    def _cooldown_allows(self, event: MarketEvent, state_value_bps: float | None) -> bool:
        key = (event.symbol.upper(), event.timeframe.upper())
        previous_time = self._last_ai_request.get(key)
        previous_state = self._last_ai_state.get(key)
        state_changed = (
            state_value_bps is not None
            and previous_state is not None
            and abs(state_value_bps - previous_state) >= self.thresholds.min_state_change_bps
        )
        if previous_time is not None:
            elapsed = (event.timestamp - previous_time).total_seconds()
            if elapsed < self.thresholds.ai_cooldown_seconds and not state_changed:
                return False
        self._last_ai_request[key] = event.timestamp
        if state_value_bps is not None:
            self._last_ai_state[key] = state_value_bps
        return True
