"""Controlled strategy registry backed by the research experience store.

Research outcomes remain evidence. The registry's status is deliberately an
execution-lifecycle status, and APPROVED is not reachable from this layer by
itself; a separate deterministic approval gate must authorize it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .memory import ExperienceStore


STRATEGY_STATUSES = {"CANDIDATE", "APPROVED", "RETIRED", "BLOCKED"}


@dataclass(frozen=True)
class Strategy:
    name: str
    version: str
    status: str
    hypothesis: dict[str, Any]
    research_state: str = "RESEARCH"
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
        if not self.research_state.strip():
            raise ValueError("research_state is required")
        if self.status == "APPROVED" and not self.approved_at_utc:
            raise ValueError("approved strategy requires approved_at_utc")
        if self.status != "APPROVED" and self.approved_at_utc is not None:
            raise ValueError("non-approved strategy cannot have approved_at_utc")


class StrategyRegistry:
    """Thin policy layer over the persistent strategy table."""

    def __init__(self, store: ExperienceStore):
        self.store = store

    def register(self, strategy: Strategy) -> None:
        strategy.validate()
        payload = dict(strategy.hypothesis)
        payload["research_state"] = strategy.research_state
        self.store.register_strategy(
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            status=strategy.status,
            hypothesis=payload,
            approved_at_utc=strategy.approved_at_utc,
            notes=strategy.notes,
        )

    def set_research_state(self, name: str, version: str, research_state: str, reason: str = "") -> None:
        existing = self._require(name, version)
        if existing["status"] != "CANDIDATE":
            raise ValueError("research state cannot be changed for non-candidate strategy")
        hypothesis = dict(existing["hypothesis"])
        hypothesis["research_state"] = research_state
        self.store.register_strategy(
            strategy_name=name,
            strategy_version=version,
            status=existing["status"],
            hypothesis=hypothesis,
            approved_at_utc=existing["approved_at_utc"],
            notes=reason or existing["notes"],
        )

    def approve(self, name: str, version: str, reason: str = "") -> None:
        """Record approval only after an external deterministic approval gate passes."""
        existing = self._require(name, version)
        if existing["hypothesis"].get("research_state") != "OOS_VALIDATED":
            raise ValueError("strategy must be OOS_VALIDATED before approval")
        self.store.register_strategy(
            strategy_name=name,
            strategy_version=version,
            status="APPROVED",
            hypothesis=existing["hypothesis"],
            approved_at_utc=datetime.now(timezone.utc).isoformat(),
            notes=reason,
        )

    def retire(self, name: str, version: str, reason: str = "") -> None:
        self._set_lifecycle(name, version, "RETIRED", reason)

    def block(self, name: str, version: str, reason: str) -> None:
        self._set_lifecycle(name, version, "BLOCKED", reason)

    def _set_lifecycle(self, name: str, version: str, status: str, reason: str) -> None:
        existing = self._require(name, version)
        self.store.register_strategy(
            strategy_name=name,
            strategy_version=version,
            status=status,
            hypothesis=existing["hypothesis"],
            approved_at_utc=existing["approved_at_utc"] if status == "APPROVED" else None,
            notes=reason,
        )

    def _require(self, name: str, version: str) -> dict[str, Any]:
        existing = self.store.get_strategy(name, version)
        if existing is None:
            raise KeyError(f"unknown strategy: {name}:{version}")
        return existing
