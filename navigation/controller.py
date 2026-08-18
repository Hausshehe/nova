"""Deterministic navigation controller built around observe/resolve/act/verify."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional, Tuple

from .actions import ActionResult, activate_node, scroll
from .observer import observe_screen
from .progress import Progress, compare_snapshots
from .resolver import TargetMatch, resolve_target
from .state import ObservationQuality, Resolution, ScreenSnapshot
from .verifier import VerificationResult, verify_transition


class NavigationState(str, Enum):
    START = "START"
    OBSERVE = "OBSERVE"
    RESOLVE_TARGET = "RESOLVE_TARGET"
    ACTIVATE = "ACTIVATE"
    WAIT_FOR_TRANSITION = "WAIT_FOR_TRANSITION"
    VERIFY = "VERIFY"
    SEARCH_VISIBLE = "SEARCH_VISIBLE"
    SCROLL = "SCROLL"
    WAIT_AFTER_SCROLL = "WAIT_AFTER_SCROLL"
    REOBSERVE = "REOBSERVE"
    RECOVER = "RECOVER"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


@dataclass(frozen=True)
class NavigationResult:
    success: bool
    verified: bool
    target: str
    state: NavigationState
    snapshot: Optional[ScreenSnapshot] = None
    match: Optional[TargetMatch] = None
    action: Optional[ActionResult] = None
    verification: Optional[VerificationResult] = None
    progress: Optional[Progress] = None
    scroll_count: int = 0
    direction: str = "down"
    message: str = ""
    history: Tuple[NavigationState, ...] = field(default_factory=tuple)


class NavigationController:
    """Bounded adaptive controller that never reverses on one bad observation."""

    def __init__(
        self,
        *,
        observation_retries: int = 2,
        verification_timeout: float = 3.0,
        settle_seconds: float = 0.25,
        max_scrolls: int = 8,
        no_progress_before_reversal: int = 2,
        max_transient_observations: int = 4,
        max_activation_retries: int = 1,
    ):
        self.observation_retries = max(1, int(observation_retries))
        self.verification_timeout = max(0.1, float(verification_timeout))
        self.settle_seconds = max(0.0, float(settle_seconds))
        self.max_scrolls = max(0, min(int(max_scrolls), 20))
        self.no_progress_before_reversal = max(2, int(no_progress_before_reversal))
        self.max_transient_observations = max(1, int(max_transient_observations))
        self.max_activation_retries = max(0, min(int(max_activation_retries), 2))

    def _result(
        self,
        *,
        target: str,
        state: NavigationState,
        history: list[NavigationState],
        snapshot: Optional[ScreenSnapshot] = None,
        match: Optional[TargetMatch] = None,
        action: Optional[ActionResult] = None,
        verification: Optional[VerificationResult] = None,
        progress: Optional[Progress] = None,
        scroll_count: int = 0,
        direction: str = "down",
        success: bool = False,
        message: str = "",
    ) -> NavigationResult:
        return NavigationResult(
            success=success,
            verified=success,
            target=target,
            state=state,
            snapshot=snapshot,
            match=match,
            action=action,
            verification=verification,
            progress=progress,
            scroll_count=scroll_count,
            direction=direction,
            message=message,
            history=tuple(history),
        )

    def _bounded_observation_failure(
        self,
        target,
        history,
        snapshot,
        progress,
        scroll_count,
        direction,
        message,
    ):
        history.append(NavigationState.RECOVER)
        return self._result(
            target=target,
            state=NavigationState.FAILURE,
            history=history,
            snapshot=snapshot,
            progress=progress,
            scroll_count=scroll_count,
            direction=direction,
            message=message,
        )

    def _activate_with_bounded_recovery(
        self,
        target: str,
        snapshot: ScreenSnapshot,
        match: TargetMatch,
        *,
        installed_packages: Optional[Iterable[str]],
        expected_foreground_package: Optional[str],
        history: list[NavigationState],
        total_scrolls: int,
        direction: str,
        progress: Optional[Progress],
    ) -> NavigationResult:
        """Activate a target, allowing only bounded re-observe/re-resolve retries."""
        current_snapshot = snapshot
        current_match = match
        last_action: Optional[ActionResult] = None
        last_verification: Optional[VerificationResult] = None

        for attempt in range(self.max_activation_retries + 1):
            history.append(NavigationState.ACTIVATE)
            last_action = activate_node(current_match.node)
            if not last_action.success:
                history.append(NavigationState.RECOVER)
                return self._result(
                    target=target,
                    state=NavigationState.FAILURE,
                    history=history,
                    snapshot=current_snapshot,
                    match=current_match,
                    action=last_action,
                    scroll_count=total_scrolls,
                    direction=direction,
                    message=last_action.message,
                )

            history.extend((NavigationState.WAIT_FOR_TRANSITION, NavigationState.VERIFY))
            last_verification = verify_transition(
                current_snapshot,
                expected_foreground_package=expected_foreground_package,
                timeout_seconds=self.verification_timeout,
            )
            if last_verification.success:
                history.append(NavigationState.SUCCESS)
                return self._result(
                    target=target,
                    state=NavigationState.SUCCESS,
                    history=history,
                    snapshot=last_verification.snapshot,
                    match=current_match,
                    action=last_action,
                    verification=last_verification,
                    progress=progress,
                    scroll_count=total_scrolls,
                    direction=direction,
                    success=True,
                    message="Target activated and the resulting UI transition was verified.",
                )

            if attempt >= self.max_activation_retries:
                break

            history.append(NavigationState.RECOVER)
            recovery_snapshot = observe_screen(
                previous=current_snapshot,
                include_nodes=True,
                retries=self.observation_retries,
                settle_seconds=self.settle_seconds,
            )
            if recovery_snapshot.observation_quality is not ObservationQuality.VALID:
                return self._bounded_observation_failure(
                    target,
                    history,
                    recovery_snapshot,
                    progress,
                    total_scrolls,
                    direction,
                    "Activation verification failed and the recovery observation was unreliable.",
                )

            recovery_match = resolve_target(
                recovery_snapshot,
                target,
                installed_packages=installed_packages,
            )
            if recovery_match.resolution is not Resolution.FOUND or recovery_match.node is None:
                return self._result(
                    target=target,
                    state=NavigationState.FAILURE,
                    history=history,
                    snapshot=recovery_snapshot,
                    match=recovery_match,
                    action=last_action,
                    verification=last_verification,
                    progress=progress,
                    scroll_count=total_scrolls,
                    direction=direction,
                    message=(
                        "Activation verification failed and the target was not safely "
                        "re-resolved for a bounded retry."
                    ),
                )

            current_snapshot = recovery_snapshot
            current_match = recovery_match

        return self._result(
            target=target,
            state=NavigationState.FAILURE,
            history=history + [NavigationState.RECOVER],
            snapshot=last_verification.snapshot if last_verification else current_snapshot,
            match=current_match,
            action=last_action,
            verification=last_verification,
            progress=progress,
            scroll_count=total_scrolls,
            direction=direction,
            message=(last_verification.reason if last_verification else "Activation verification failed."),
        )

    def navigate_target(
        self,
        target: str,
        *,
        installed_packages: Optional[Iterable[str]] = None,
        expected_foreground_package: Optional[str] = None,
        initial_direction: str = "down",
    ) -> NavigationResult:
        history = [NavigationState.START]
        snapshot: Optional[ScreenSnapshot] = None
        total_scrolls = 0
        current_direction = str(initial_direction or "down").strip().lower()
        if current_direction not in {"up", "down"}:
            current_direction = "down"
        no_progress = 0
        transient_observations = 0
        last_progress: Optional[Progress] = None

        while total_scrolls <= self.max_scrolls:
            history.append(NavigationState.OBSERVE)
            snapshot = observe_screen(
                previous=snapshot,
                include_nodes=True,
                retries=self.observation_retries,
                settle_seconds=self.settle_seconds,
            )
            if snapshot.observation_quality is not ObservationQuality.VALID:
                transient_observations += 1
                history.append(NavigationState.REOBSERVE)
                if transient_observations >= self.max_transient_observations:
                    return self._bounded_observation_failure(
                        target,
                        history,
                        snapshot,
                        last_progress,
                        total_scrolls,
                        current_direction,
                        "Android UI observations remained unreliable within the bounded recovery budget.",
                    )
                continue
            transient_observations = 0

            history.append(NavigationState.RESOLVE_TARGET)
            match = resolve_target(
                snapshot,
                target,
                installed_packages=installed_packages,
            )
            if match.resolution in {Resolution.INVALID_OBSERVATION, Resolution.AMBIGUOUS}:
                return self._result(
                    target=target,
                    state=NavigationState.FAILURE,
                    history=history + [NavigationState.RECOVER],
                    snapshot=snapshot,
                    match=match,
                    scroll_count=total_scrolls,
                    direction=current_direction,
                    message=match.reason,
                )

            if match.resolution is Resolution.FOUND and match.node is not None:
                return self._activate_with_bounded_recovery(
                    target,
                    snapshot,
                    match,
                    installed_packages=installed_packages,
                    expected_foreground_package=expected_foreground_package,
                    history=history,
                    total_scrolls=total_scrolls,
                    direction=current_direction,
                    progress=last_progress,
                )

            history.append(NavigationState.SEARCH_VISIBLE)
            if not snapshot.scrollable:
                return self._result(
                    target=target,
                    state=NavigationState.FAILURE,
                    history=history + [NavigationState.RECOVER],
                    snapshot=snapshot,
                    match=match,
                    progress=last_progress,
                    scroll_count=total_scrolls,
                    direction=current_direction,
                    message="Target is not visible and the current screen exposes no live scrollable region.",
                )
            if total_scrolls >= self.max_scrolls:
                break

            history.append(NavigationState.SCROLL)
            action = scroll(snapshot, current_direction)
            if not action.success:
                history.append(NavigationState.REOBSERVE)
                recovery_snapshot = observe_screen(
                    previous=snapshot,
                    include_nodes=True,
                    retries=self.observation_retries,
                    settle_seconds=self.settle_seconds,
                )
                if recovery_snapshot.observation_quality is not ObservationQuality.VALID:
                    transient_observations += 1
                    if transient_observations >= self.max_transient_observations:
                        return self._bounded_observation_failure(
                            target,
                            history,
                            recovery_snapshot,
                            last_progress,
                            total_scrolls,
                            current_direction,
                            "Repeated transient observations prevented safe scroll recovery.",
                        )
                    continue
                no_progress += 1
            else:
                total_scrolls += 1
                history.append(NavigationState.WAIT_AFTER_SCROLL)
                time.sleep(self.settle_seconds)
                history.append(NavigationState.REOBSERVE)
                after = observe_screen(
                    previous=snapshot,
                    include_nodes=True,
                    retries=self.observation_retries,
                    settle_seconds=self.settle_seconds,
                )
                if after.observation_quality is not ObservationQuality.VALID:
                    transient_observations += 1
                    if transient_observations >= self.max_transient_observations:
                        return self._bounded_observation_failure(
                            target,
                            history,
                            after,
                            last_progress,
                            total_scrolls,
                            current_direction,
                            "Repeated transient observations prevented safe post-scroll verification.",
                        )
                    continue
                transient_observations = 0
                last_progress = compare_snapshots(snapshot, after)
                snapshot = after
                if last_progress.meaningful:
                    no_progress = 0
                else:
                    confirm = observe_screen(
                        previous=snapshot,
                        include_nodes=True,
                        retries=self.observation_retries,
                        settle_seconds=self.settle_seconds,
                    )
                    if confirm.observation_quality is not ObservationQuality.VALID:
                        transient_observations += 1
                        if transient_observations >= self.max_transient_observations:
                            return self._bounded_observation_failure(
                                target,
                                history,
                                confirm,
                                last_progress,
                                total_scrolls,
                                current_direction,
                                "Repeated transient observations prevented safe progress assessment.",
                            )
                        continue
                    confirmation = compare_snapshots(snapshot, confirm)
                    snapshot = confirm
                    if confirmation.meaningful:
                        last_progress = confirmation
                        no_progress = 0
                    else:
                        no_progress += 1

            if no_progress >= self.no_progress_before_reversal:
                if current_direction == "down":
                    current_direction = "up"
                    no_progress = 0
                    continue
                break

        history.append(NavigationState.FAILURE)
        return self._result(
            target=target,
            state=NavigationState.FAILURE,
            history=history,
            snapshot=snapshot,
            progress=last_progress,
            scroll_count=total_scrolls,
            direction=current_direction,
            message="Target was not found within the bounded adaptive navigation budget.",
        )
