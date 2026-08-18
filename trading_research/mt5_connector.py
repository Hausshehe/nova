"""Read-only MetaTrader 5 market-data adapter.

This module deliberately has no order/execution functions. Gate 0 is about
proving that Nova can obtain trustworthy historical market data before any
strategy or trading automation is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


class MT5Unavailable(RuntimeError):
    """Raised when the optional MetaTrader5 package cannot be imported."""


class MT5ConnectionError(RuntimeError):
    """Raised when the MetaTrader 5 terminal cannot be initialized."""


@dataclass(frozen=True)
class MT5Config:
    path: Optional[str] = None
    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    timeout_ms: int = 60_000
    portable: bool = False


class MT5MarketData:
    """Small, injectable read-only gateway around the official MT5 Python API."""

    def __init__(self, config: Optional[MT5Config] = None, module: Any = None):
        self.config = config or MT5Config()
        self._module = module
        self._connected = False

    @property
    def module(self) -> Any:
        if self._module is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise MT5Unavailable(
                    "MetaTrader5 is not installed in this Python environment. "
                    "This connector is intended for the supported Windows environment."
                ) from exc
            self._module = mt5
        return self._module

    def connect(self) -> None:
        mt5 = self.module
        kwargs = {
            "timeout": int(self.config.timeout_ms),
            "portable": bool(self.config.portable),
        }
        if self.config.login is not None:
            kwargs["login"] = int(self.config.login)
        if self.config.password is not None:
            kwargs["password"] = self.config.password
        if self.config.server is not None:
            kwargs["server"] = self.config.server

        if self.config.path:
            ok = mt5.initialize(self.config.path, **kwargs)
        else:
            ok = mt5.initialize(**kwargs)

        if not ok:
            raise MT5ConnectionError(f"MetaTrader 5 initialize() failed: {mt5.last_error()}")
        self._connected = True

    def close(self) -> None:
        if self._module is not None and self._connected:
            self._module.shutdown()
        self._connected = False

    def __enter__(self) -> "MT5MarketData":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_connection(self) -> Any:
        if not self._connected:
            raise MT5ConnectionError("MT5 connector is not connected.")
        return self.module

    def bars(
        self,
        symbol: str,
        timeframe: int,
        date_from: datetime,
        date_to: datetime,
    ) -> Any:
        """Return raw MT5 bars for a UTC interval; never mutates trading state."""
        if not symbol or not str(symbol).strip():
            raise ValueError("symbol must be non-empty")
        if date_from.tzinfo is None or date_to.tzinfo is None:
            raise ValueError("date_from and date_to must be timezone-aware")
        if date_from >= date_to:
            raise ValueError("date_from must be earlier than date_to")

        mt5 = self._require_connection()
        utc_from = date_from.astimezone(timezone.utc)
        utc_to = date_to.astimezone(timezone.utc)
        result = mt5.copy_rates_range(symbol.strip(), timeframe, utc_from, utc_to)
        if result is None:
            raise MT5ConnectionError(f"copy_rates_range() failed: {mt5.last_error()}")
        return result

    def ticks(
        self,
        symbol: str,
        date_from: datetime,
        date_to: datetime,
        flags: int,
    ) -> Any:
        """Return raw MT5 ticks for a UTC interval; never submits orders."""
        if not symbol or not str(symbol).strip():
            raise ValueError("symbol must be non-empty")
        if date_from.tzinfo is None or date_to.tzinfo is None:
            raise ValueError("date_from and date_to must be timezone-aware")
        if date_from >= date_to:
            raise ValueError("date_from must be earlier than date_to")

        mt5 = self._require_connection()
        utc_from = date_from.astimezone(timezone.utc)
        utc_to = date_to.astimezone(timezone.utc)
        result = mt5.copy_ticks_range(symbol.strip(), utc_from, utc_to, flags)
        if result is None:
            raise MT5ConnectionError(f"copy_ticks_range() failed: {mt5.last_error()}")
        return result
