"""Post-execution journal and deterministic trading kill switch.

The journal records execution outcomes into Nova's existing experience memory.
The kill switch is fail-closed: once tripped, execution is refused until it is
explicitly reset by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .execution import ExecutionRequest, ExecutionResult
from .memory import ExperienceStore, TradeRecord


@dataclass(frozen=True)
class KillSwitchState:
    tripped: bool = False
    reason: str = ""
    tripped_at_utc: str | None = None


class TradingKillSwitch:
    """Fail-closed circuit breaker for autonomous execution."""

    def __init__(self) -> None:
        self._state = KillSwitchState()

    @property
    def state(self) -> KillSwitchState:
        return self._state

    def trip(self, reason: str) -> None:
        reason = reason.strip()
        if not reason:
            raise ValueError("kill-switch reason is required")
        self._state = KillSwitchState(
            tripped=True,
            reason=reason,
            tripped_at_utc=datetime.now(timezone.utc).isoformat(),
        )

    def reset(self) -> None:
        self._state = KillSwitchState()

    def allow_execution(self) -> bool:
        return not self._state.tripped

    def require_clear(self) -> None:
        if self._state.tripped:
            raise RuntimeError(f"trading kill switch is active: {self._state.reason}")


class TradeJournal:
    """Persist demo/live execution outcomes as experience records."""

    def __init__(self, store: ExperienceStore):
        self.store = store

    def record_execution(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
        *,
        timeframe: str,
        direction: str,
        outcome: str = "OPEN",
        exit_price: float | None = None,
        pnl: float | None = None,
        closed_at: str | None = None,
        notes: str = "",
        market_state: dict | None = None,
    ) -> TradeRecord | None:
        if not result.accepted:
            return None
        if not timeframe.strip() or timeframe.upper() == "UNKNOWN":
            raise ValueError("trade timeframe is required and cannot be UNKNOWN")
        if direction not in {"LONG", "SHORT"}:
            raise ValueError("trade direction must be LONG or SHORT")

        recommendation = request.recommendation
        strategy_name = recommendation.strategy_name
        strategy_version = recommendation.strategy_version
        if not strategy_name or not strategy_version:
            raise ValueError("executed trade requires strategy identity")

        trade = TradeRecord(
            trade_id=result.execution_id,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            symbol=request.symbol.strip().upper(),
            timeframe=timeframe.strip().upper(),
            direction=direction,
            entry_price=request.price,
            exit_price=exit_price,
            quantity=request.quantity,
            pnl=pnl,
            outcome=outcome,
            opened_at=request.timestamp_utc.astimezone(timezone.utc).isoformat(),
            closed_at=closed_at,
            market_state=market_state or {},
            notes=notes,
        )
        self.store.record_trade(trade)
        return trade
