"""Controlled strategy registry backed by the research experience store.

The registry remembers strategy identity, version, research status, and provenance.
It never grants execution authority; execution eligibility is a separate concern.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .memory import ExperienceStore


STRATEGY_STATUSES = {
    "RESEARCH",
    "REJECTED",
    "INCONCLUSIVE",
    "PROMISING",
    "OOS_VALIDATED",
    "APPROVED",
    "RETIRED",
    "BLOCKED",
}


@dataclass(frozen=True)
class Strategy:
    name: str
    version: str
    status: str
    hypothesis: dict[str, Any]
    notes: str = ""
    approved_at_utc: str | None = None

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("strategy name is required")
        if not self.version.strip():
            raise ValueError("strategy version is required")
        if self.status not in STRATEGY_STATUSES:
            raise ValueError(f"unsupported strategy status: {self.status}")
        if not isinstance(self.hypothesis, dict) or not self.hypothesis:
            raise ValueError("strategy hypothesis must be a non-empty object")
        if self.status == "APPROVED" and not self.approved_at_utc:
            raise ValueError("approved strategy requires approved_at_utc")


class StrategyRegistry:
    """Thin policy layer over the persistent strategy table."""

    def __init__(self, store: ExperienceStore):
        self.store = store

    def register(self, strategy: Strategy) -> None:
        strategy.validate()
        self.store.register_strategy(
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            status=strategy.status,
            hypothesis=strategy.hypothesis,
            approved_at_utc=strategy.approved_at_utc,
            notes=strategy.notes,
        )

    def mark_rejected(self, name: str, version: str, reason: str) -> None:
        self._set_status(name, version, "REJECTED", reason)

    def mark_inconclusive(self, name: str, version: str, reason: str) -> None:
        self._set_status(name, version, "INCONCLUSIVE", reason)

    def mark_promising(self, name: str, version: str, reason: str) -> None:
        self._set_status(name, version, "PROMISING", reason)

    def mark_oos_validated(self, name: str, version: str, reason: str) -> None:
        self._set_status(name, version, "OOS_VALIDATED", reason)

    def approve(self, name: str, version: str, reason: str = "") -> None:
        """Record approval only after an external deterministic approval gate passes."""
        self._set_status(
            name,
            version,
            "APPROVED",
            reason,
            approved_at_utc=datetime.now(timezone.utc).isoformat(),
        )

    def retire(self, name: str, version: str, reason: str = "") -> None:
        self._set_status(name, version, "RETIRED", reason)

    def block(self, name: str, version: str, reason: str) -> None:
        self._set_status(name, version, "BLOCKED", reason)

    def _set_status(
        self,
        name: str,
        version: str,
        status: str,
        reason: str,
        *,
        approved_at_utc: str | None = None,
    ) -> None:
        if status not in STRATEGY_STATUSES:
            raise ValueError(f"unsupported strategy status: {status}")
        existing = self.store.get_strategy(name, version)
        if existing is None:
            raise KeyError(f"unknown strategy: {name}:{version}")
        self.store.register_strategy(
            strategy_name=name,
            strategy_version=version,
            status=status,
            hypothesis=existing["hypothesis"],
            approved_at_utc=approved_at_utc if status == "APPROVED" else existing["approved_at_utc"],
            notes=reason,
        )
