"""Strictly demo-gated MetaTrader 5 execution adapter.

This adapter is intentionally separate from the read-only MT5 market-data
connector. It refuses to operate unless the connected terminal explicitly
reports demo trading mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .execution import ExecutionRequest, ExecutionResult


class DemoExecutionUnavailable(RuntimeError):
    """Raised when MT5 demo execution cannot be safely established."""


@dataclass(frozen=True)
class MT5DemoExecutionConfig:
    path: str | None = None
    timeout_ms: int = 60_000
    portable: bool = False


class MT5DemoExecutionGateway:
    """Send orders only after the terminal proves it is in demo mode."""

    environment = "MT5_DEMO"

    def __init__(self, config: MT5DemoExecutionConfig | None = None, module: Any = None):
        self.config = config or MT5DemoExecutionConfig()
        self._module = module
        self._connected = False

    @property
    def module(self) -> Any:
        if self._module is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise DemoExecutionUnavailable(
                    "MetaTrader5 is unavailable; demo execution requires the MT5 environment."
                ) from exc
            self._module = mt5
        return self._module

    def connect(self) -> None:
        mt5 = self.module
        kwargs = {
            "timeout": int(self.config.timeout_ms),
            "portable": bool(self.config.portable),
        }
        ok = (
            mt5.initialize(self.config.path, **kwargs)
            if self.config.path
            else mt5.initialize(**kwargs)
        )
        if not ok:
            raise DemoExecutionUnavailable(f"MT5 initialize() failed: {mt5.last_error()}")

        info = mt5.account_info()
        if info is None:
            mt5.shutdown()
            raise DemoExecutionUnavailable(f"MT5 account_info() failed: {mt5.last_error()}")

        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", object())
        if getattr(info, "trade_mode", None) != demo_mode:
            mt5.shutdown()
            raise DemoExecutionUnavailable("connected MT5 account is not explicitly in DEMO mode")
        self._connected = True

    def close(self) -> None:
        if self._module is not None and self._connected:
            self._module.shutdown()
        self._connected = False

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        request.validate()
        if request.recommendation.action not in {"ENTER", "EXIT"}:
            return ExecutionResult(False, "", "execution requires ENTER or EXIT", self.environment)
        if not self._connected:
            raise DemoExecutionUnavailable("MT5 demo gateway is not connected")

        mt5 = self.module
        symbol = request.symbol.strip()
        if not mt5.symbol_select(symbol, True):
            raise DemoExecutionUnavailable(f"symbol_select() failed for {symbol}: {mt5.last_error()}")

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise DemoExecutionUnavailable(f"symbol_info_tick() failed: {mt5.last_error()}")

        order_type = (
            getattr(mt5, "ORDER_TYPE_BUY")
            if request.recommendation.action == "ENTER"
            else getattr(mt5, "ORDER_TYPE_SELL")
        )
        live_price = float(getattr(tick, "ask" if request.recommendation.action == "ENTER" else "bid"))
        order = {
            "action": getattr(mt5, "TRADE_ACTION_DEAL"),
            "symbol": symbol,
            "volume": float(request.quantity),
            "type": order_type,
            "price": live_price,
            "deviation": 20,
            "magic": 260819,
            "comment": "Nova DEMO",
            "type_time": getattr(mt5, "ORDER_TIME_GTC"),
            "type_filling": getattr(mt5, "ORDER_FILLING_IOC"),
        }

        check = mt5.order_check(order)
        if check is None:
            raise DemoExecutionUnavailable(f"order_check() failed: {mt5.last_error()}")

        check_retcode = getattr(check, "retcode", None)
        success_code = getattr(mt5, "TRADE_RETCODE_DONE", check_retcode)
        if check_retcode not in {0, success_code}:
            raise DemoExecutionUnavailable(f"order_check() rejected request: retcode={check_retcode}")

        result = mt5.order_send(order)
        if result is None:
            raise DemoExecutionUnavailable(f"order_send() returned no result: {mt5.last_error()}")

        retcode = getattr(result, "retcode", None)
        if retcode != getattr(mt5, "TRADE_RETCODE_DONE", retcode):
            return ExecutionResult(
                accepted=False,
                execution_id=str(getattr(result, "order", "")),
                message=f"MT5 demo order rejected: retcode={retcode}",
                environment=self.environment,
            )

        return ExecutionResult(
            accepted=True,
            execution_id=str(getattr(result, "order", "")),
            message="MT5 demo order sent and accepted",
            environment=self.environment,
        )
