"""Versioned trading constitution separate from Nova's core identity rules.

The constitution governs trading-system behavior that may evolve through
research. It does not redefine Nova's general identity, language, or non-trading
behavior. Changes are explicit and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class TradingConstitution:
    version: str = "1.0"
    normal_review_seconds: int = 15
    minimum_review_seconds: int = 1
    maximum_review_seconds: int = 60
    max_daily_loss_fraction: float = 0.02
    max_open_positions: int = 3
    max_spread_bps: float = 25.0
    session_start: time = time(8, 0)
    session_end: time = time(16, 0)
    demo_only: bool = True
    require_approved_strategy: bool = True
    require_structured_ai_decision: bool = True
    require_deterministic_policy: bool = True
    require_kill_switch: bool = True

    def validate(self) -> None:
        if not self.version.strip():
            raise ValueError("version is required")
        if self.minimum_review_seconds <= 0:
            raise ValueError("minimum_review_seconds must be positive")
        if self.normal_review_seconds < self.minimum_review_seconds:
            raise ValueError("normal_review_seconds is below minimum")
        if self.maximum_review_seconds < self.normal_review_seconds:
            raise ValueError("maximum_review_seconds is below normal review interval")
        if self.max_daily_loss_fraction <= 0:
            raise ValueError("max_daily_loss_fraction must be positive")
        if self.max_open_positions < 0:
            raise ValueError("max_open_positions cannot be negative")
        if self.max_spread_bps <= 0:
            raise ValueError("max_spread_bps must be positive")
        if self.session_start >= self.session_end:
            raise ValueError("session_start must be before session_end")

    def review_interval_for(self, recommended_seconds: int | None) -> int:
        """Clamp dynamic escalation timing to constitution-approved bounds."""
        candidate = self.normal_review_seconds if recommended_seconds is None else recommended_seconds
        return max(self.minimum_review_seconds, min(self.maximum_review_seconds, int(candidate)))

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "normal_review_seconds": self.normal_review_seconds,
            "minimum_review_seconds": self.minimum_review_seconds,
            "maximum_review_seconds": self.maximum_review_seconds,
            "max_daily_loss_fraction": self.max_daily_loss_fraction,
            "max_open_positions": self.max_open_positions,
            "max_spread_bps": self.max_spread_bps,
            "session_start": self.session_start.isoformat(),
            "session_end": self.session_end.isoformat(),
            "demo_only": self.demo_only,
            "require_approved_strategy": self.require_approved_strategy,
            "require_structured_ai_decision": self.require_structured_ai_decision,
            "require_deterministic_policy": self.require_deterministic_policy,
            "require_kill_switch": self.require_kill_switch,
        }
