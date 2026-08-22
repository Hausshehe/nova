"""Bounded observation-driven recovery for Android navigation.

Recovery is deliberately finite: one initial action, at most two observations,
and at most one recovery action. No open-ended retry loop is permitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar

from .state import ObservationQuality, ScreenSnapshot


T = TypeVar("T")

MAX_OBSERVATIONS = 2
MAX_RECOVERY_ACTIONS = 1


@dataclass(frozen=True)
class RecoveryResult(Generic[T]):
    success: bool
    value: Optional[T]
    snapshot: Optional[ScreenSnapshot]
    observations: int
    recovery_actions: int
    reason: str


def run_bounded_recovery(
    *,
    initial_action: Callable[[], T],
    observe: Callable[[Optional[ScreenSnapshot]], ScreenSnapshot],
    success_predicate: Callable[[ScreenSnapshot], bool],
    recovery_action: Optional[Callable[[ScreenSnapshot], T]] = None,
    max_observations: int = MAX_OBSERVATIONS,
    max_recovery_actions: int = MAX_RECOVERY_ACTIONS,
) -> RecoveryResult[T]:
    """Execute one action and recover from transient UI failure with hard bounds.

    The recovery action is attempted only after a fresh observation proves that
    the expected state has not yet been reached. The function never retries the
    recovery action more than once and never performs more observations than the
    configured bounded budget.
    """
    observation_budget = max(1, min(int(max_observations), MAX_OBSERVATIONS))
    recovery_budget = max(0, min(int(max_recovery_actions), MAX_RECOVERY_ACTIONS))

    value = initial_action()
    previous: Optional[ScreenSnapshot] = None
    observations = 0
    recovery_actions = 0

    for _ in range(observation_budget):
        snapshot = observe(previous)
        observations += 1
        previous = snapshot

        if snapshot.observation_quality is ObservationQuality.VALID and success_predicate(snapshot):
            return RecoveryResult(
                True,
                value,
                snapshot,
                observations,
                recovery_actions,
                "Expected state reached within the bounded verification budget.",
            )

        if recovery_action is not None and recovery_actions < recovery_budget:
            value = recovery_action(snapshot)
            recovery_actions += 1

    return RecoveryResult(
        False,
        value,
        previous,
        observations,
        recovery_actions,
        "Expected state was not reached before the bounded recovery budget was exhausted.",
    )
