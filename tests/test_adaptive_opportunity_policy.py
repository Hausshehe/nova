from datetime import datetime, timedelta, timezone

import pytest

from trading_research.adaptive_opportunity_policy import build_walk_forward_policy
from trading_research.data import Bar


def _bars(count: int, *, close: float = 1.0) -> tuple[Bar, ...]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        Bar(
            timestamp=start + timedelta(minutes=15 * index),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1.0,
        )
        for index in range(count)
    )


def test_adaptive_filter_never_invents_requests_outside_candidates() -> None:
    bars = _bars(80)
    candidates = {10, 25, 40, 60}

    decisions = build_walk_forward_policy(
        bars,
        fast_period=5,
        slow_period=10,
        candidate_indices=candidates,
        min_samples=2,
    )

    requested = {decision.index for decision in decisions if decision.request_ai}
    assert requested <= candidates


def test_trusted_candidates_are_preserved_until_enough_evidence_exists() -> None:
    bars = _bars(80)
    candidates = {index for index in range(10, 80)}

    decisions = build_walk_forward_policy(
        bars,
        future_bars=4,
        fast_period=5,
        slow_period=10,
        candidate_indices=candidates,
        min_samples=20,
        min_confidence=0.65,
    )

    early = {decision.index for decision in decisions if 10 <= decision.index < 30}
    early_requested = {
        decision.index
        for decision in decisions
        if 10 <= decision.index < 30 and decision.request_ai
    }
    assert early_requested == early

    later_suppressed = [
        decision
        for decision in decisions
        if decision.index >= 30 and decision.reason == "historically low actionable rate; adaptive suppression"
    ]
    assert later_suppressed


def test_candidate_indices_reject_out_of_range_values() -> None:
    bars = _bars(20)

    with pytest.raises(ValueError, match="out-of-range"):
        build_walk_forward_policy(
            bars,
            fast_period=3,
            slow_period=5,
            candidate_indices={20},
        )


def test_learning_is_causal_and_does_not_depend_on_distant_future() -> None:
    first = list(_bars(50))
    second = list(_bars(50))
    for index in range(30, 50):
        price = 1.0 + index * 0.01
        second[index] = Bar(
            timestamp=second[index].timestamp,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1.0,
        )

    candidates = set(range(10, 50))
    first_decisions = build_walk_forward_policy(
        first,
        future_bars=4,
        fast_period=5,
        slow_period=10,
        candidate_indices=candidates,
        min_samples=3,
    )
    second_decisions = build_walk_forward_policy(
        second,
        future_bars=4,
        fast_period=5,
        slow_period=10,
        candidate_indices=candidates,
        min_samples=3,
    )

    for index in range(10, 26):
        assert first_decisions[index] == second_decisions[index]
