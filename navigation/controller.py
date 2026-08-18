"""Deterministic navigation controller built around observe/resolve/act/verify."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional, Tuple

from .actions import ActionResult, activate_node
from .observer import observe_screen
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
    message: str = ""
    history: Tuple[NavigationState, ...] = field(default_factory=tuple)


class NavigationController:
    """Small controller that refuses to act on invalid/transient observations."""

    def __init__(self, *, observation_retries: int = 2, verification_timeout: float = 3.0):
        self.observation_retries = max(1, int(observation_retries))
        self.verification_timeout = max(0.1, float(verification_timeout))

    def navigate_target(
        self,
        target: str,
        *,
        installed_packages: Optional[Iterable[str]] = None,
        expected_foreground_package: Optional[str] = None,
    ) -> NavigationResult:
        history = [NavigationState.START]
        previous: Optional[ScreenSnapshot] = None

        history.append(NavigationState.OBSERVE)
        snapshot = observe_screen(previous=previous, include_nodes=True, retries=self.observation_retries)
        if snapshot.observation_quality is not ObservationQuality.VALID:
            history.append(NavigationState.RECOVER)
            return NavigationResult(
                False,
                False,
                target,
                NavigationState.FAILURE,
                snapshot=snapshot,
                message="Navigation paused because the current observation is not valid.",
                history=tuple(history),
            )

        history.append(NavigationState.RESOLVE_TARGET)
        match = resolve_target(snapshot, target, installed_packages=installed_packages)
        if match.resolution is Resolution.INVALID_OBSERVATION:
            history.append(NavigationState.RECOVER)
            return NavigationResult(
                False,
                False,
                target,
                NavigationState.FAILURE,
                snapshot=snapshot,
                match=match,
                message=match.reason,
                history=tuple(history),
            )

        if match.resolution is not Resolution.FOUND or match.node is None:
            history.append(NavigationState.SEARCH_VISIBLE)
            return NavigationResult(
                False,
                False,
                target,
                NavigationState.SEARCH_VISIBLE,
                snapshot=snapshot,
                match=match,
                message="Target is not currently visible; scrolling is deliberately handled by the next controller layer.",
                history=tuple(history),
            )

        history.append(NavigationState.ACTIVATE)
        action = activate_node(match.node)
        if not action.success:
            history.append(NavigationState.RECOVER)
            return NavigationResult(
                False,
                False,
                target,
                NavigationState.FAILURE,
                snapshot=snapshot,
                match=match,
                action=action,
                message=action.message,
                history=tuple(history),
            )

        history.append(NavigationState.WAIT_FOR_TRANSITION)
        history.append(NavigationState.VERIFY)
        verification = verify_transition(
            snapshot,
            expected_foreground_package=expected_foreground_package,
            timeout_seconds=self.verification_timeout,
        )
        if not verification.success:
            history.append(NavigationState.RECOVER)
            return NavigationResult(
                False,
                False,
                target,
                NavigationState.FAILURE,
                snapshot=verification.snapshot,
                match=match,
                action=action,
                verification=verification,
                message=verification.reason,
                history=tuple(history),
            )

        history.append(NavigationState.SUCCESS)
        return NavigationResult(
            True,
            True,
            target,
            NavigationState.SUCCESS,
            snapshot=verification.snapshot,
            match=match,
            action=action,
            verification=verification,
            message="Target activated and the resulting UI transition was verified.",
            history=tuple(history),
        )
