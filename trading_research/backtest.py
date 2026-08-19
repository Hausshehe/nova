"""Small deterministic long/flat research backtester.

The engine is intentionally narrow. A signal is evaluated at bar *i* and,
when it changes, the position is executed at bar *i+1* open. This prevents a
strategy from using the current bar's close/high/low to magically trade at that
same bar's price.

No live trading, broker access, or order placement belongs in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .data import Bar


Signal = Callable[[Sequence[Bar], int], bool]


@dataclass(frozen=True)
class Trade:
    entry_timestamp: object
    exit_timestamp: object
    entry_price: float
    exit_price: float
    return_fraction: float


@dataclass(frozen=True)
class BacktestResult:
    trades: Sequence[Trade]
    equity_curve: Sequence[float]
    final_return: float
    max_drawdown: float
    profit_factor: float
    expectancy: float
    win_rate: float
    average_win: float
    average_loss: float


def _profit_factor(returns: Sequence[float]) -> float:
    gains = sum(value for value in returns if value > 0)
    losses = -sum(value for value in returns if value < 0)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _max_drawdown(equity: Sequence[float]) -> float:
    peak = 1.0
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def run_long_flat(
    bars: Sequence[Bar],
    signal: Signal,
    *,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> BacktestResult:
    """Backtest a boolean long/flat signal with next-bar-open execution.

    ``signal(bars, i)`` describes the desired state after observing bar ``i``.
    A position change is executed at the next bar's open, so the final bar
    cannot create a new position. Any open position is closed at the final
    close. Returns are fractional and start from equity=1.0.

    The equity curve is marked to market on every bar while a position is open;
    this ensures maximum drawdown includes unrealized intra-trade losses.
    """
    if len(bars) < 2:
        raise ValueError("at least two bars are required")
    if fee_bps < 0 or slippage_bps < 0:
        raise ValueError("fee_bps and slippage_bps cannot be negative")

    cost = (fee_bps + slippage_bps) / 10_000.0
    in_position = False
    entry_price = 0.0
    entry_timestamp = None
    realized_equity = 1.0
    equity_curve = [realized_equity]
    trades: list[Trade] = []

    for index in range(len(bars) - 1):
        desired = bool(signal(bars, index))
        next_bar = bars[index + 1]

        if not in_position and desired:
            entry_price = next_bar.open * (1.0 + cost)
            entry_timestamp = next_bar.timestamp
            in_position = True
        elif in_position and not desired:
            exit_price = next_bar.open * (1.0 - cost)
            trade_return = exit_price / entry_price - 1.0
            realized_equity *= 1.0 + trade_return
            trades.append(
                Trade(
                    entry_timestamp=entry_timestamp,
                    exit_timestamp=next_bar.timestamp,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    return_fraction=trade_return,
                )
            )
            in_position = False
            entry_price = 0.0
            entry_timestamp = None

        marked_equity = realized_equity
        if in_position:
            marked_equity = realized_equity * (next_bar.close / entry_price)
        equity_curve.append(marked_equity)

    if in_position:
        exit_bar = bars[-1]
        exit_price = exit_bar.close * (1.0 - cost)
        trade_return = exit_price / entry_price - 1.0
        realized_equity *= 1.0 + trade_return
        trades.append(
            Trade(
                entry_timestamp=entry_timestamp,
                exit_timestamp=exit_bar.timestamp,
                entry_price=entry_price,
                exit_price=exit_price,
                return_fraction=trade_return,
            )
        )
        equity_curve.append(realized_equity)

    returns = [trade.return_fraction for trade in trades]
    winning = [value for value in returns if value > 0]
    losing = [value for value in returns if value < 0]
    expectancy = sum(returns) / len(returns) if returns else 0.0

    return BacktestResult(
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
        final_return=realized_equity - 1.0,
        max_drawdown=_max_drawdown(equity_curve),
        profit_factor=_profit_factor(returns),
        expectancy=expectancy,
        win_rate=len(winning) / len(returns) if returns else 0.0,
        average_win=sum(winning) / len(winning) if winning else 0.0,
        average_loss=sum(losing) / len(losing) if losing else 0.0,
    )
