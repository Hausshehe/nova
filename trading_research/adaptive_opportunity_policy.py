"""Walk-forward adaptive policy for selective strategy-aware AI escalation."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable, Sequence

from .data import Bar


@dataclass(frozen=True)
class AdaptivePolicyDecision:
    index: int
    request_ai: bool
    confidence: float
    bucket: tuple[int, int, int]
    reason: str


def _features(
    bars: Sequence[Bar],
    index: int,
    *,
    fast_period: int,
    slow_period: int,
    momentum_lookback: int,
) -> tuple[float, float, float]:
    if index + 1 < slow_period:
        return 0.0, 0.0, 0.0
    fast = sum(x.close for x in bars[index - fast_period + 1:index + 1]) / fast_period
    slow = sum(x.close for x in bars[index - slow_period + 1:index + 1]) / slow_period
    gap = abs(fast / slow - 1.0) * 10_000.0 if slow else 0.0
    start = max(0, index - momentum_lookback)
    momentum = abs(bars[index].close / bars[start].close - 1.0) * 10_000.0 if bars[start].close else 0.0
    gap_slope = 0.0
    if index >= momentum_lookback and start + 1 >= slow_period:
        start_fast = sum(x.close for x in bars[start - fast_period + 1:start + 1]) / fast_period
        start_slow = sum(x.close for x in bars[start - slow_period + 1:start + 1]) / slow_period
        start_gap = abs(start_fast / start_slow - 1.0) * 10_000.0 if start_slow else 0.0
        gap_slope = gap - start_gap
    return momentum, gap, gap_slope


def build_walk_forward_policy(
    bars: Sequence[Bar],
    *,
    future_bars: int = 4,
    opportunity_move_bps: float = 30.0,
    transaction_cost_bps_round_trip: float = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
    momentum_lookback: int = 3,
    min_samples: int = 20,
    min_confidence: float = 0.65,
    bucket_width_bps: float = 5.0,
    candidate_indices: Iterable[int] | None = None,
) -> tuple[AdaptivePolicyDecision, ...]:
    """Build a causal adaptive *filter* over an optional trusted candidate set.

    When ``candidate_indices`` is supplied, the adaptive policy can only
    suppress requests from that set; it can never invent a new request outside
    the trusted baseline. Candidates are preserved by default until enough
    historical evidence exists to justify suppression. This makes the adaptive
    layer an efficiency optimizer rather than a replacement opportunity
    detector.

    Labels are added only after the decision for the current bar and require a
    complete future horizon. Therefore the decision at bar ``N`` only uses
    outcomes that were observable by ``N`` and never uses future information.
    """
    if future_bars <= 0 or opportunity_move_bps <= 0 or transaction_cost_bps_round_trip < 0:
        raise ValueError("invalid opportunity parameters")
    if fast_period <= 0 or slow_period <= fast_period or momentum_lookback <= 0:
        raise ValueError("invalid feature periods")
    if min_samples <= 0 or not 0 < min_confidence <= 1 or bucket_width_bps <= 0:
        raise ValueError("invalid adaptive policy parameters")

    if candidate_indices is None:
        candidates: set[int] | None = None
    else:
        candidates = set(candidate_indices)
        invalid = [index for index in candidates if index < 0 or index >= len(bars)]
        if invalid:
            raise ValueError("candidate_indices contains an out-of-range index")

    history: dict[tuple[int, int, int], deque[bool]] = defaultdict(lambda: deque(maxlen=500))
    results: list[AdaptivePolicyDecision] = []
    actionable_threshold = opportunity_move_bps + transaction_cost_bps_round_trip
    non_actionable_floor = 1.0 - min_confidence

    for index in range(len(bars)):
        momentum, gap, slope = _features(
            bars,
            index,
            fast_period=fast_period,
            slow_period=slow_period,
            momentum_lookback=momentum_lookback,
        )
        bucket = (
            int(momentum // bucket_width_bps),
            int(gap // bucket_width_bps),
            int(abs(slope) // bucket_width_bps),
        )
        prior = history[bucket]
        enough_evidence = len(prior) >= min_samples
        confidence = sum(prior) / len(prior) if enough_evidence else 0.0
        is_candidate = candidates is None or index in candidates

        if not is_candidate:
            request = False
            reason = "outside trusted candidate set"
        elif not enough_evidence:
            request = True
            reason = "insufficient evidence; preserve trusted candidate"
        elif confidence <= non_actionable_floor:
            request = False
            reason = "historically low actionable rate; adaptive suppression"
        else:
            request = True
            reason = "historically actionable feature state"

        results.append(AdaptivePolicyDecision(index, request, confidence, bucket, reason))

        # Do not train on an incomplete horizon. This avoids making the tail of
        # a replay behave differently merely because fewer future bars exist.
        future = bars[index + 1:index + 1 + future_bars]
        if len(future) < future_bars or index + 1 < slow_period:
            continue

        move = max(abs(next_bar.close / bars[index].close - 1.0) * 10_000.0 for next_bar in future)
        label = False
        if move >= actionable_threshold:
            fast = sum(x.close for x in bars[index - fast_period + 1:index + 1]) / fast_period
            slow = sum(x.close for x in bars[index - slow_period + 1:index + 1]) / slow_period
            label = fast != slow
        history[bucket].append(label)

    return tuple(results)
