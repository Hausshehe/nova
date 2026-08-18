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
    ):
        self.observation_retries = max(1, int(observation_retries))
        self.verification_timeout = max(0.1, float(verification_timeout))
        self.settle_seconds = max(0.0, float(settle_seconds))
        self.max_scrolls = max(0, min(int(max_scrolls), 20))
        self.no_progress_before_reversal = max(2, int(no_progress_before_reversal))

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

    def navigate_target(
        self,
        target: str,
        *,
        installed_packages: Optional[Iterable[str]] = None,
        expected_foreground_package: Optional[str] = None,
    ) -> NavigationResult:
        history = [NavigationState.START]
        snapshot: Optional[ScreenSnapshot] = None
        total_scrolls = 0
        directions = ("down", "up")
        current_direction = directions[0]
        no_progress = 0
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
                history.append(NavigationState.REOBSERVE)
                continue

            history.append(NavigationState.RESOLVE_TARGET)
            match = resolve_target(snapshot, target, installed_packages=installed_packages)
            if match.resolution is Resolution.INVALID_OBSERVATION:
                history.append(NavigationState.RECOVER)
                return self._result(
                    target=target,
                    state=NavigationState.FAILURE,
                    history=history,
                    snapshot=snapshot,
                    match=match,
                    scroll_count=total_scrolls,
                    direction=current_direction,
                    message=match.reason,
                )

            if match.resolution is Resolution.FOUND and match.node is not None:
                history.append(NavigationState.ACTIVATE)
                action = activate_node(match.node)
                if not action.success:
                    history.append(NavigationState.RECOVER)
                    return self._result(
                        target=target,
                        state=NavigationState.FAILURE,
                        history=history,
                        snapshot=snapshot,
                        match=match,
                        action=action,
                        scroll_count=total_scrolls,
                        direction=current_direction,
                        message=action.message,
                    )

                history.append(NavigationState.WAIT_FOR_TRANSITION)
                history.append(NavigationState.VERIFY)
                verification = verify_transition(
                    snapshot,
                    expected_foreground_package=expected_foreground_package,
                    timeout_seconds=self.verification_timeout,
                )
                if verification.success:
                    history.append(NavigationState.SUCCESS)
                    return self._result(
                        target=target,
                        state=NavigationState.SUCCESS,
                        history=history,
                        snapshot=verification.snapshot,
                        match=match,
                        action=action,
                        verification=verification,
                        progress=last_progress,
                        scroll_count=total_scrolls,
                        direction=current_direction,
                        success=True,
                        message="Target activated and the resulting UI transition was verified.",
                    )

                history.append(NavigationState.RECOVER)
                return self._result(
                    target=target,
                    state=NavigationState.FAILURE,
                    history=history,
                    snapshot=verification.snapshot,
                    match=match,
                    action=action,
                    verification=verification,
                    progress=last_progress,
                    scroll_count=total_scrolls,
                    direction=current_direction,
                    message=verification.reason,
                )

            history.append(NavigationState.SEARCH_VISIBLE)
            if not snapshot.scrollable:
                history.append(NavigationState.RECOVER)
                return self._result(
                    target=target,
                    state=NavigationState.FAILURE,
                    history=history,
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
                if recovery_snapshot.observation_quality is ObservationQuality.TRANSIENT:
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
                    # A transient result never counts as a failed scroll.
                    snapshot = after
                    continue

                last_progress = compare_snapshots(snapshot, after)
                snapshot = after
                if last_progress.meaningful:
                    no_progress = 0
                else:
                    # Re-observe once before declaring a real stall.
                    confirm = observe_screen(
                        previous=snapshot,
                        include_nodes=True,
                        retries=self.observation_retries,
                        settle_seconds=self.settle_seconds,
                    )
                    if confirm.observation_quality is ObservationQuality.VALID:
                        confirmation = compare_snapshots(snapshot, confirm)
                        snapshot = confirm
                        if confirmation.meaningful:
                            last_progress = confirmation
                            no_progress = 0
                        else:
                            no_progress += 1
                    else:
                        snapshot = confirm
                        continue

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
