"""Causal historical outcome ledger for market-research replay.

The ledger records only information that would be unavailable before a bar's
future window is complete under an explicitly labeled outcome section. The
feature/decision fields are time-of-decision data; outcome fields are strictly
post-decision evaluation labels.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

from .data import Bar


@dataclass(frozen=True)
class OutcomeRecord:
    index: int
    timestamp: str
    entry_close: float
    future_bars: int
    opportunity_move_bps: float
    transaction_cost_bps: float
    fast_period: int
    slow_period: int
    history_available: bool
    sma_fast: float | None
    sma_slow: float | None
    sma_gap_bps: float | None
    terminal_close_return_bps: float | None
    max_up_close_move_bps: float | None
    max_down_close_move_bps: float | None
    max_abs_close_move_bps: float | None
    net_max_abs_move_bps: float | None
    opportunity_label: bool
    actionable_label: bool
    insufficient_future_window: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_outcome_ledger(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    transaction_cost_bps_round_trip: float = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
) -> list[OutcomeRecord]:
    """Build one causal record per bar with future outcomes kept as labels."""
    if future_bars <= 0:
        raise ValueError("future_bars must be positive")
    if opportunity_move_bps <= 0:
        raise ValueError("opportunity_move_bps must be positive")
    if transaction_cost_bps_round_trip < 0:
        raise ValueError("transaction_cost_bps_round_trip cannot be negative")
    if fast_period <= 0 or slow_period <= fast_period:
        raise ValueError("slow_period must exceed fast_period")

    records: list[OutcomeRecord] = []
    for index, bar in enumerate(bars):
        future = bars[index + 1 : index + 1 + future_bars]
        insufficient_future_window = len(future) < future_bars

        history_available = index + 1 >= slow_period
        sma_fast: float | None = None
        sma_slow: float | None = None
        sma_gap_bps: float | None = None
        if history_available:
            sma_fast = sum(x.close for x in bars[index - fast_period + 1 : index + 1]) / fast_period
            sma_slow = sum(x.close for x in bars[index - slow_period + 1 : index + 1]) / slow_period
            sma_gap_bps = (sma_fast / sma_slow - 1.0) * 10_000

        terminal_return = None
        max_up = max_down = max_abs = None
        opportunity_label = False
        actionable_label = False
        if future:
            terminal_return = (future[-1].close / bar.close - 1.0) * 10_000
            up_moves = [(next_bar.close / bar.close - 1.0) * 10_000 for next_bar in future]
            down_moves = [(bar.close / next_bar.close - 1.0) * 10_000 for next_bar in future]
            max_up = max(up_moves)
            max_down = max(down_moves)
            max_abs = max(abs((next_bar.close / bar.close - 1.0) * 10_000) for next_bar in future)
            net_max = max_abs - transaction_cost_bps_round_trip
            opportunity_label = max_abs >= opportunity_move_bps
            actionable_label = (
                opportunity_label
                and net_max >= opportunity_move_bps
                and history_available
                and sma_fast != sma_slow
            )
        else:
            net_max = None

        records.append(
            OutcomeRecord(
                index=index,
                timestamp=bar.timestamp.isoformat(),
                entry_close=bar.close,
                future_bars=future_bars,
                opportunity_move_bps=opportunity_move_bps,
                transaction_cost_bps=transaction_cost_bps_round_trip,
                fast_period=fast_period,
                slow_period=slow_period,
                history_available=history_available,
                sma_fast=sma_fast,
                sma_slow=sma_slow,
                sma_gap_bps=sma_gap_bps,
                terminal_close_return_bps=terminal_return,
                max_up_close_move_bps=max_up,
                max_down_close_move_bps=max_down,
                max_abs_close_move_bps=max_abs,
                net_max_abs_move_bps=net_max,
                opportunity_label=opportunity_label,
                actionable_label=actionable_label,
                insufficient_future_window=insufficient_future_window,
            )
        )

    return records


__all__ = ["OutcomeRecord", "build_outcome_ledger"]
