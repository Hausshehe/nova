"""Causal diagnostics for why the SMA directional baseline loses money."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean, median
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .outcome_ledger import build_outcome_ledger


@dataclass(frozen=True)
class DirectionalBucket:
    bucket: str
    bars: int
    mean_return_bps: float
    mean_net_return_bps: float
    positive_net_rate: float
    target_hit_rate: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _bucket(records, indices: set[int], cost: float, name: str) -> DirectionalBucket:
    rows = [
        r for r in records
        if r.index in indices
        and not r.insufficient_future_window
        and r.sma_gap_bps is not None
        and r.sma_gap_bps != 0
    ]
    returns: list[float] = []
    hits: list[bool] = []
    for r in rows:
        future_index = r.index + r.future_bars
        returns_bps = None
        if future_index < len(records):
            future_entry = records[future_index].entry_close
            if future_entry > 0:
                raw = (future_entry / r.entry_close - 1.0) * 10_000.0
                returns_bps = raw if r.sma_gap_bps > 0 else -raw
        if returns_bps is not None:
            returns.append(returns_bps)
            hits.append(r.max_abs_close_move_bps is not None and r.max_abs_close_move_bps >= r.opportunity_move_bps)
    net = [value - cost for value in returns]
    return DirectionalBucket(
        bucket=name,
        bars=len(returns),
        mean_return_bps=mean(returns) if returns else 0.0,
        mean_net_return_bps=mean(net) if net else 0.0,
        positive_net_rate=sum(v > 0 for v in net) / len(net) if net else 0.0,
        target_hit_rate=sum(hits) / len(hits) if hits else 0.0,
    )


def evaluate_directional_failure_diagnostics(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    transaction_cost_bps: float = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
    folds: int = 4,
) -> dict[str, object]:
    records = build_outcome_ledger(
        bars,
        future_bars=future_bars,
        opportunity_move_bps=opportunity_move_bps,
        transaction_cost_bps_round_trip=transaction_cost_bps,
        fast_period=fast_period,
        slow_period=slow_period,
    )
    candidates = high_recall_candidate_indices(bars, fast_period=fast_period, slow_period=slow_period)
    long_indices = {r.index for r in records if r.index in candidates and r.sma_gap_bps is not None and r.sma_gap_bps > 0}
    short_indices = {r.index for r in records if r.index in candidates and r.sma_gap_bps is not None and r.sma_gap_bps < 0}

    abs_gap = [(abs(r.sma_gap_bps), r.index) for r in records if r.index in candidates and r.sma_gap_bps is not None and r.sma_gap_bps != 0]
    strong = {i for gap, i in abs_gap if gap >= 20.0}
    weak = {i for gap, i in abs_gap if gap < 20.0}

    n = len(bars)
    fold_size = n // folds
    chronological = []
    for fold in range(folds):
        start = fold * fold_size
        end = n if fold == folds - 1 else (fold + 1) * fold_size
        fold_set = {i for i in candidates if start <= i < end}
        chronological.append({
            "fold": fold + 1,
            "all": _bucket(records, fold_set, transaction_cost_bps, "all").to_dict(),
            "long": _bucket(records, fold_set & long_indices, transaction_cost_bps, "long").to_dict(),
            "short": _bucket(records, fold_set & short_indices, transaction_cost_bps, "short").to_dict(),
        })

    return {
        "policy": "causal_directional_baseline_failure_diagnostics",
        "candidate_bars": len(candidates),
        "full_sample": {
            "all": _bucket(records, candidates, transaction_cost_bps, "all").to_dict(),
            "long": _bucket(records, long_indices, transaction_cost_bps, "long").to_dict(),
            "short": _bucket(records, short_indices, transaction_cost_bps, "short").to_dict(),
            "strong_sma_gap_abs_bps_ge_20": _bucket(records, strong, transaction_cost_bps, "strong").to_dict(),
            "weak_sma_gap_abs_bps_lt_20": _bucket(records, weak, transaction_cost_bps, "weak").to_dict(),
        },
        "chronological_folds": chronological,
        "causal_rule": "Direction uses current/past SMA state only; four-bar close outcome is evaluation-only.",
    }
