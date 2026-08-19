"""Walk-forward adaptive policy for selective strategy-aware AI escalation."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .data import Bar


@dataclass(frozen=True)
class AdaptivePolicyDecision:
    index: int
    request_ai: bool
    confidence: float
    bucket: tuple[int, ...]
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
    fast = sum(x.close for x in bars[index - fast_period + 1 : index + 1]) / fast_period
    slow = sum(x.close for x in bars[index - slow_period + 1 : index + 1]) / slow_period
    gap = abs(fast / slow - 1.0) * 10_000.0 if slow else 0.0
    start = max(0, index - momentum_lookback)
    momentum = abs(bars[index].close / bars[start].close - 1.0) * 10_000.0 if bars[start].close else 0.0
    gap_slope = 0.0
    if index >= momentum_lookback and start + 1 >= slow_period:
        start_fast = sum(x.close for x in bars[start - fast_period + 1 : start + 1]) / fast_period
        start_slow = sum(x.close for x in bars[start - slow_period + 1 : start + 1]) / slow_period
        start_gap = abs(start_fast / start_slow - 1.0) * 10_000.0 if start_slow else 0.0
        gap_slope = gap - start_gap
    return momentum, gap, gap_slope


def _bucket_for(
    bars: Sequence[Bar],
    index: int,
    *,
    fast_period: int,
    slow_period: int,
    momentum_lookback: int,
    bucket_width_bps: float,
    observable_context: Mapping[int, tuple[int, int]] | None = None,
) -> tuple[int, ...]:
    momentum, gap, slope = _features(
        bars,
        index,
        fast_period=fast_period,
        slow_period=slow_period,
        momentum_lookback=momentum_lookback,
    )
    bucket: tuple[int, ...] = (
        int(momentum // bucket_width_bps),
        int(gap // bucket_width_bps),
        int(abs(slope) // bucket_width_bps),
    )
    if observable_context is not None:
        tier_code, reason_code = observable_context.get(index, (-1, -1))
        bucket += (tier_code, reason_code)
    return bucket


def _label_at(
    bars: Sequence[Bar],
    index: int,
    *,
    future_bars: int,
    actionable_threshold: float,
    fast_period: int,
    slow_period: int,
) -> bool | None:
    """Return a label only when the full future horizon is now observable."""
    future = bars[index + 1 : index + 1 + future_bars]
    if len(future) < future_bars or index + 1 < slow_period:
        return None

    move = max(abs(next_bar.close / bars[index].close - 1.0) * 10_000.0 for next_bar in future)
    if move < actionable_threshold:
        return False

    fast = sum(x.close for x in bars[index - fast_period + 1 : index + 1]) / fast_period
    slow = sum(x.close for x in bars[index - slow_period + 1 : index + 1]) / slow_period
    return fast != slow


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
    bucket_width_bps: float = 25.0,
    candidate_indices: Iterable[int] | None = None,
    observable_context: Mapping[int, tuple[int, int]] | None = None,
) -> tuple[AdaptivePolicyDecision, ...]:
    """Build a causal adaptive filter over a trusted candidate set."""
    if future_bars <= 0 or opportunity_move_bps <= 0 or transaction_cost_bps_round_trip < 0:
        raise ValueError("invalid opportunity parameters")
    if fast_period <= 0:
        raise ValueError("fast_period must be positive")
    if slow_period <= fast_period:
        raise ValueError("slow_period must exceed fast_period")
    if momentum_lookback <= 0:
        raise ValueError("momentum_lookback must be positive")
    if min_samples <= 0:
        raise ValueError("min_samples must be positive")
    if not 0 < min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1")
    if bucket_width_bps <= 0:
        raise ValueError("bucket_width_bps must be positive")

    if candidate_indices is None:
        candidates: set[int] | None = None
    else:
        candidates = set(candidate_indices)
        invalid = [index for index in candidates if index < 0 or index >= len(bars)]
        if invalid:
            raise ValueError("candidate_indices contains an out-of-range index")

    if observable_context is not None:
        invalid_context = [index for index in observable_context if index < 0 or index >= len(bars)]
        if invalid_context:
            raise ValueError("observable_context contains an out-of-range index")

    history: dict[tuple[int, ...], deque[bool]] = defaultdict(lambda: deque(maxlen=500))
    context_history: dict[tuple[int, int], deque[bool]] = defaultdict(lambda: deque(maxlen=500))
    tier_history: dict[int, deque[bool]] = defaultdict(lambda: deque(maxlen=500))
    results: list[AdaptivePolicyDecision] = []
    actionable_threshold = opportunity_move_bps + transaction_cost_bps_round_trip
    non_actionable_floor = 1.0 - min_confidence

    for index in range(len(bars)):
        label_index = index - future_bars
        if label_index >= 0:
            label = _label_at(
                bars,
                label_index,
                future_bars=future_bars,
                actionable_threshold=actionable_threshold,
                fast_period=fast_period,
                slow_period=slow_period,
            )
            if label is not None:
                context = observable_context.get(label_index) if observable_context is not None else None
                bucket = _bucket_for(
                    bars,
                    label_index,
                    fast_period=fast_period,
                    slow_period=slow_period,
                    momentum_lookback=momentum_lookback,
                    bucket_width_bps=bucket_width_bps,
                    observable_context=observable_context,
                )
                history[bucket].append(label)
                if context is not None:
                    tier_code, reason_code = context
                    context_history[(tier_code, reason_code)].append(label)
                    tier_history[tier_code].append(label)

        bucket = _bucket_for(
            bars,
            index,
            fast_period=fast_period,
            slow_period=slow_period,
            momentum_lookback=momentum_lookback,
            bucket_width_bps=bucket_width_bps,
            observable_context=observable_context,
        )
        prior = history[bucket]
        evidence_source = "exact feature/context state"

        if len(prior) < min_samples and observable_context is not None:
            context = observable_context.get(index)
            if context is not None and len(context_history[context]) >= min_samples:
                prior = context_history[context]
                evidence_source = "observable context state"
            elif context is not None and len(tier_history[context[0]]) >= min_samples:
                prior = tier_history[context[0]]
                evidence_source = "strategy confidence tier"

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
            reason = f"historically low actionable rate; adaptive suppression ({evidence_source})"
        else:
            request = True
            reason = f"historically actionable feature state ({evidence_source})"

        results.append(AdaptivePolicyDecision(index, request, confidence, bucket, reason))

    return tuple(results)
