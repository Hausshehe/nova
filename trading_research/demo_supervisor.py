"""Fail-safe supervisor for Nova's demo trading session.

The supervisor does not create orders. It decides whether the execution layer is
healthy enough to be called, based on data freshness, broker connectivity,
reconciliation, and explicit demo-mode status.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .trade_safety import TradingKillSwitch


@dataclass(frozen=True)
class SupervisorSnapshot:
    healthy: bool
    reasons: tuple[str, ...]
    checked_at_utc: str


@dataclass(frozen=True)
class SupervisorConfig:
    max_market_data_age_seconds: float = 30.0
    require_demo_mode: bool = True


class DemoTradingSupervisor:
    """Guard autonomous demo execution with deterministic health checks."""

    def __init__(
        self,
        *,
        config: SupervisorConfig | None = None,
        kill_switch: TradingKillSwitch | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or SupervisorConfig()
        self.kill_switch = kill_switch or TradingKillSwitch()
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._last_snapshot = SupervisorSnapshot(False, ("not_checked",), self._utc_now().isoformat())

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @property
    def last_snapshot(self) -> SupervisorSnapshot:
        return self._last_snapshot

    def check(
        self,
        *,
        market_timestamp: datetime,
        broker_connected: bool,
        demo_mode: bool,
        reconciled: bool,
        reference_time: datetime | None = None,
    ) -> SupervisorSnapshot:
        """Check live health, or use reference_time for deterministic replay."""
        now = reference_time.astimezone(timezone.utc) if reference_time is not None else self._utc_now()
        reasons: list[str] = []

        timestamp = market_timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp = timestamp.astimezone(timezone.utc)
        age = (now - timestamp).total_seconds()
        if age < 0:
            reasons.append("market_data_timestamp_in_future")
        elif age > self.config.max_market_data_age_seconds:
            reasons.append(f"stale_market_data:{age:.1f}s>{self.config.max_market_data_age_seconds:.1f}s")

        if not broker_connected:
            reasons.append("broker_disconnected")
        if self.config.require_demo_mode and not demo_mode:
            reasons.append("demo_mode_required")
        if not reconciled:
            reasons.append("account_not_reconciled")
        if not self.kill_switch.allow_execution():
            reasons.append("trading_kill_switch_active")

        healthy = not reasons
        self._last_snapshot = SupervisorSnapshot(healthy, tuple(reasons), now.isoformat())
        if not healthy:
            self.kill_switch.trip("; ".join(reasons))
        return self._last_snapshot

    def require_healthy(self) -> None:
        if not self._last_snapshot.healthy:
            raise RuntimeError("demo trading supervisor is not healthy: " + "; ".join(self._last_snapshot.reasons))
        self.kill_switch.require_clear()
