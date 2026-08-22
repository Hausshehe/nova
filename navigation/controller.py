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
    STABILIZE = "STABILIZE"
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

    def __init__(self, *, observation_retries: int = 2, verification_timeout: float = 3.0, settle_seconds: float = 0.45, max_scrolls: int = 8, no_progress_before_reversal: int = 2, max_transient_observations: int = 4, max_activation_retries: int = 1):
        self.observation_retries = max(1, int(observation_retries))
        self.verification_timeout = max(0.1, float(verification_timeout))
        self.settle_seconds = max(0.0, float(settle_seconds))
        self.max_scrolls = max(0, min(int(max_scrolls), 20))
        self.no_progress_before_reversal = max(2, int(no_progress_before_reversal))
        self.max_transient_observations = max(1, int(max_transient_observations))
        self.max_activation_retries = max(0, min(int(max_activation_retries), 2))

    def _result(self, *, target: str, state: NavigationState, history: list[NavigationState], snapshot: Optional[ScreenSnapshot] = None, match: Optional[TargetMatch] = None, action: Optional[ActionResult] = None, verification: Optional[VerificationResult] = None, progress: Optional[Progress] = None, scroll_count: int = 0, direction: str = "down", success: bool = False, message: str = "") -> NavigationResult:
        return NavigationResult(success=success, verified=success, target=target, state=state, snapshot=snapshot, match=match, action=action, verification=verification, progress=progress, scroll_count=scroll_count, direction=direction, message=message, history=tuple(history))

    def _bounded_observation_failure(self, target, history, snapshot, progress, scroll_count, direction, message):
        history.append(NavigationState.RECOVER)
        return self._result(target=target, state=NavigationState.FAILURE, history=history, snapshot=snapshot, progress=progress, scroll_count=scroll_count, direction=direction, message=message)

    def _source_target_label_present(self, snapshot: ScreenSnapshot, match: TargetMatch) -> bool:
        source_label = " ".join(str(match.label or "").split()).lower()
        if not source_label:
            return False
        for node in snapshot.visible_nodes:
            if not isinstance(node, dict) or not node.get("enabled", True):
                continue
            label = str(node.get("text") or "").strip() or str(node.get("content_description") or "").strip() or str(node.get("resource_id") or "").strip()
            if " ".join(label.split()).lower() == source_label:
                return True
        return False

    def _refresh_activation_target(self, snapshot: ScreenSnapshot, target: str, *, installed_packages: Optional[Iterable[str]]) -> tuple[ScreenSnapshot, Optional[TargetMatch]]:
        time.sleep(self.settle_seconds)
        refreshed = observe_screen(previous=snapshot, include_nodes=True, retries=self.observation_retries, settle_seconds=self.settle_seconds)
        if refreshed.observation_quality is not ObservationQuality.VALID:
            return refreshed, None
        refreshed_match = resolve_target(refreshed, target, installed_packages=installed_packages)
        if refreshed_match.resolution is Resolution.FOUND and refreshed_match.node is not None:
            return refreshed, refreshed_match
        return refreshed, None

    def _stable_start_observation(self, history: list[NavigationState]) -> Optional[ScreenSnapshot]:
        """Acquire a fresh, usable starting hierarchy before target resolution.

        This deliberately does not pass an old snapshot to the observer. Launching
        an Android activity can briefly expose a stale/empty accessibility tree, and
        navigation must not interpret that transient state as the initial screen.
        """
        history.append(NavigationState.STABILIZE)
        time.sleep(self.settle_seconds)
        first = observe_screen(previous=None, include_nodes=True, retries=self.observation_retries, settle_seconds=self.settle_seconds)
        if first.observation_quality is ObservationQuality.VALID:
            return first
        time.sleep(self.settle_seconds)
        second = observe_screen(previous=None, include_nodes=True, retries=self.observation_retries + 1, settle_seconds=self.settle_seconds)
        if second.observation_quality is ObservationQuality.VALID:
            return second
        return None

    def _fresh_post_action_observation(self, *, previous: ScreenSnapshot, history: list[NavigationState]) -> ScreenSnapshot:
        """Observe the live UI after an action without reusing stale node data."""
        history.append(NavigationState.REOBSERVE)
        observed = observe_screen(previous=None, include_nodes=True, retries=self.observation_retries, settle_seconds=self.settle_seconds)
        if observed.observation_quality is ObservationQuality.VALID:
            return observed
        # A second fresh attempt gets a larger retry budget but still never copies
        # the pre-action hierarchy into the result.
        time.sleep(self.settle_seconds)
        return observe_screen(previous=None, include_nodes=True, retries=self.observation_retries + 1, settle_seconds=self.settle_seconds)

    def _activate_with_bounded_recovery(self, target: str, snapshot: ScreenSnapshot, match: TargetMatch, *, installed_packages: Optional[Iterable[str]], expected_foreground_package: Optional[str], history: list[NavigationState], total_scrolls: int, direction: str, progress: Optional[Progress]) -> NavigationResult:
        current_snapshot = snapshot
        current_match = match
        last_action: Optional[ActionResult] = None
        last_verification: Optional[VerificationResult] = None
        re_resolved = False
        for attempt in range(self.max_activation_retries + 1):
            history.append(NavigationState.ACTIVATE)
            last_action = activate_node(current_match.node)
            if not last_action.success:
                geometry_mismatch = "Actionable ancestor bounds do not contain the target bounds." in last_action.message
                if geometry_mismatch and attempt < self.max_activation_retries:
                    history.append(NavigationState.RECOVER)
                    fresh = self._fresh_post_action_observation(previous=current_snapshot, history=history)
                    if fresh.observation_quality is not ObservationQuality.VALID:
                        return self._bounded_observation_failure(target, history, fresh, progress, total_scrolls, direction, "Activation geometry was inconsistent and the fresh recovery observation was unreliable.")
                    fresh_match = resolve_target(fresh, target, installed_packages=installed_packages)
                    if fresh_match.resolution is not Resolution.FOUND or fresh_match.node is None:
                        return self._result(target=target, state=NavigationState.FAILURE, history=history, snapshot=fresh, match=fresh_match, action=last_action, scroll_count=total_scrolls, direction=direction, message="Activation geometry was inconsistent and the target could not be safely re-resolved for the bounded retry.")
                    current_snapshot, current_match, re_resolved = fresh, fresh_match, True
                    continue
                history.append(NavigationState.RECOVER)
                return self._result(target=target, state=NavigationState.FAILURE, history=history, snapshot=current_snapshot, match=current_match, action=last_action, scroll_count=total_scrolls, direction=direction, message=last_action.message)
            history.extend((NavigationState.WAIT_FOR_TRANSITION, NavigationState.VERIFY))
            last_verification = verify_transition(current_snapshot, expected_foreground_package=expected_foreground_package, expected_target=target, timeout_seconds=self.verification_timeout)
            if last_verification.success:
                history.append(NavigationState.SUCCESS)
                return self._result(target=target, state=NavigationState.SUCCESS, history=history, snapshot=last_verification.snapshot, match=current_match, action=last_action, verification=last_verification, progress=progress, scroll_count=total_scrolls, direction=direction, success=True, message="Target activated and the resulting UI transition was verified.")
            if attempt >= self.max_activation_retries:
                break
            history.append(NavigationState.RECOVER)
            recovery_snapshot = self._fresh_post_action_observation(previous=current_snapshot, history=history)
            if recovery_snapshot.observation_quality is not ObservationQuality.VALID:
                return self._bounded_observation_failure(target, history, recovery_snapshot, progress, total_scrolls, direction, "Activation verification failed and the recovery observation was unreliable.")
            recovery_progress = compare_snapshots(current_snapshot, recovery_snapshot)
            source_target_present = self._source_target_label_present(recovery_snapshot, current_match)
            if recovery_progress.meaningful and not source_target_present:
                recovered_verification = VerificationResult(True, recovery_snapshot, "A meaningful live UI transition was verified during bounded activation recovery after the activated source control disappeared.")
                history.extend((NavigationState.VERIFY, NavigationState.SUCCESS))
                return self._result(target=target, state=NavigationState.SUCCESS, history=history, snapshot=recovery_snapshot, match=current_match, action=last_action, verification=recovered_verification, progress=progress, scroll_count=total_scrolls, direction=direction, success=True, message="Target activated and the resulting UI transition was verified during bounded recovery.")
            recovery_match = resolve_target(recovery_snapshot, target, installed_packages=installed_packages)
            if recovery_match.resolution is not Resolution.FOUND or recovery_match.node is None:
                return self._result(target=target, state=NavigationState.FAILURE, history=history, snapshot=recovery_snapshot, match=recovery_match, action=last_action, verification=last_verification, scroll_count=total_scrolls, direction=direction, message="Activation verification failed and the target was not safely re-resolved for a bounded retry.")
            current_snapshot, current_match, re_resolved = recovery_snapshot, recovery_match, True
        failure_message = "Activation verification failed after the target was safely re-resolved for the bounded retry." if re_resolved else (last_verification.reason if last_verification else "Activation verification failed.")
        return self._result(target=target, state=NavigationState.FAILURE, history=history + [NavigationState.RECOVER], snapshot=last_verification.snapshot if last_verification else current_snapshot, match=current_match, action=last_action, verification=last_verification, progress=progress, scroll_count=total_scrolls, direction=direction, message=failure_message)

    def _stabilize_after_scroll(self, snapshot: ScreenSnapshot, target: str, *, installed_packages: Optional[Iterable[str]]) -> tuple[ScreenSnapshot, Optional[TargetMatch]]:
        current = snapshot
        for _ in range(2):
            match = resolve_target(current, target, installed_packages=installed_packages)
            if match.resolution is Resolution.FOUND:
                return current, match
            if current.scrollable:
                return current, match
            current = observe_screen(previous=None, include_nodes=True, retries=self.observation_retries, settle_seconds=self.settle_seconds)
            if current.observation_quality is not ObservationQuality.VALID:
                continue
        return current, resolve_target(current, target, installed_packages=installed_packages)

    def navigate_target(self, target: str, *, installed_packages: Optional[Iterable[str]] = None, expected_foreground_package: Optional[str] = None, initial_direction: str = "down") -> NavigationResult:
        history = [NavigationState.START]
        snapshot: Optional[ScreenSnapshot] = None
        total_scrolls = 0
        current_direction = str(initial_direction or "down").strip().lower()
        if current_direction not in {"up", "down"}:
            current_direction = "down"
        no_progress = 0
        transient_observations = 0
        scroll_action_failures = 0
        scroll_distance_ratio = 0.35
        last_progress: Optional[Progress] = None

        snapshot = self._stable_start_observation(history)
        if snapshot is None:
            return self._bounded_observation_failure(target, history, None, last_progress, total_scrolls, current_direction, "Android UI did not expose a fresh usable hierarchy after bounded startup stabilization.")

        while total_scrolls <= self.max_scrolls:
            history.append(NavigationState.OBSERVE)
            if total_scrolls == 0 and snapshot is not None:
                observed = snapshot
            else:
                observed = observe_screen(previous=None, include_nodes=True, retries=self.observation_retries, settle_seconds=self.settle_seconds)
            snapshot = observed
            if snapshot.observation_quality is not ObservationQuality.VALID:
                transient_observations += 1
                history.append(NavigationState.REOBSERVE)
                if transient_observations >= self.max_transient_observations:
                    return self._bounded_observation_failure(target, history, snapshot, last_progress, total_scrolls, current_direction, "Android UI observations remained unreliable within the bounded recovery budget.")
                snapshot = None
                continue
            transient_observations = 0
            history.append(NavigationState.RESOLVE_TARGET)
            match = resolve_target(snapshot, target, installed_packages=installed_packages)
            if match.resolution in {Resolution.INVALID_OBSERVATION, Resolution.AMBIGUOUS}:
                return self._result(target=target, state=NavigationState.FAILURE, history=history + [NavigationState.RECOVER], snapshot=snapshot, match=match, scroll_count=total_scrolls, direction=current_direction, message=match.reason)
            if match.resolution is Resolution.FOUND and match.node is not None:
                return self._activate_with_bounded_recovery(target, snapshot, match, installed_packages=installed_packages, expected_foreground_package=expected_foreground_package, history=history, total_scrolls=total_scrolls, direction=current_direction, progress=last_progress)
            history.append(NavigationState.SEARCH_VISIBLE)
            if not snapshot.scrollable:
                snapshot, stabilized_match = self._stabilize_after_scroll(snapshot, target, installed_packages=installed_packages)
                if stabilized_match is not None and stabilized_match.resolution is Resolution.FOUND and stabilized_match.node is not None:
                    return self._activate_with_bounded_recovery(target, snapshot, stabilized_match, installed_packages=installed_packages, expected_foreground_package=expected_foreground_package, history=history + [NavigationState.REOBSERVE], total_scrolls=total_scrolls, direction=current_direction, progress=last_progress)
                if not snapshot.scrollable:
                    return self._result(target=target, state=NavigationState.FAILURE, history=history + [NavigationState.RECOVER], snapshot=snapshot, match=stabilized_match or match, progress=last_progress, scroll_count=total_scrolls, direction=current_direction, message="Target is not visible and the current screen exposes no live scrollable region after bounded stabilization.")
            if total_scrolls >= self.max_scrolls:
                break
            history.append(NavigationState.SCROLL)
            action = scroll(snapshot, current_direction, distance_ratio=scroll_distance_ratio)
            if not action.success:
                history.append(NavigationState.RECOVER)
                recovery_snapshot = self._fresh_post_action_observation(previous=snapshot, history=history)
                if recovery_snapshot.observation_quality is not ObservationQuality.VALID:
                    transient_observations += 1
                    if transient_observations >= self.max_transient_observations:
                        return self._bounded_observation_failure(target, history, recovery_snapshot, last_progress, total_scrolls, current_direction, "Repeated transient observations prevented safe scroll recovery.")
                    continue
                recovery_progress = compare_snapshots(snapshot, recovery_snapshot)
                if recovery_progress.meaningful:
                    # The transport said the action failed, but the live UI moved.
                    # Trust the observed world over the transport error and continue
                    # without inferring anything about scroll direction.
                    scroll_action_failures = 0
                    last_progress = recovery_progress
                    no_progress = 0
                    snapshot = recovery_snapshot
                    history.append(NavigationState.REOBSERVE)
                    continue
                scroll_action_failures += 1
                scroll_distance_ratio = max(0.20, scroll_distance_ratio * 0.70)
                if scroll_action_failures >= 2:
                    return self._result(target=target, state=NavigationState.FAILURE, history=history, snapshot=recovery_snapshot, action=action, progress=recovery_progress, scroll_count=total_scrolls, direction=current_direction, message="Scroll command was rejected twice and fresh observations show no UI progress; refusing to reverse direction without boundary evidence.")
                snapshot = recovery_snapshot
                history.append(NavigationState.REOBSERVE)
                continue

            scroll_action_failures = 0
            total_scrolls += 1
            history.append(NavigationState.WAIT_AFTER_SCROLL)
            time.sleep(self.settle_seconds)
            after = self._fresh_post_action_observation(previous=snapshot, history=history)
            if after.observation_quality is not ObservationQuality.VALID:
                transient_observations += 1
                if transient_observations >= self.max_transient_observations:
                    return self._bounded_observation_failure(target, history, after, last_progress, total_scrolls, current_direction, "Repeated transient observations prevented safe scroll recovery.")
                snapshot = None
                continue
            transient_observations = 0
            post_scroll_match = resolve_target(after, target, installed_packages=installed_packages)
            if post_scroll_match.resolution is Resolution.AMBIGUOUS:
                return self._result(target=target, state=NavigationState.FAILURE, history=history + [NavigationState.RECOVER], snapshot=after, match=post_scroll_match, action=action, scroll_count=total_scrolls, direction=current_direction, message=post_scroll_match.reason)
            if post_scroll_match.resolution is Resolution.FOUND and post_scroll_match.node is not None:
                refreshed_after, refreshed_match = self._refresh_activation_target(after, target, installed_packages=installed_packages)
                if refreshed_match is not None and refreshed_match.node is not None:
                    history.append(NavigationState.REOBSERVE)
                    return self._activate_with_bounded_recovery(target, refreshed_after, refreshed_match, installed_packages=installed_packages, expected_foreground_package=expected_foreground_package, history=history, total_scrolls=total_scrolls, direction=current_direction, progress=last_progress)
                history.append(NavigationState.REOBSERVE)
                return self._activate_with_bounded_recovery(target, after, post_scroll_match, installed_packages=installed_packages, expected_foreground_package=expected_foreground_package, history=history, total_scrolls=total_scrolls, direction=current_direction, progress=last_progress)
            stabilized_after, stabilized_match = self._stabilize_after_scroll(after, target, installed_packages=installed_packages)
            if stabilized_match is not None and stabilized_match.resolution is Resolution.FOUND and stabilized_match.node is not None:
                refreshed_stable, refreshed_match = self._refresh_activation_target(stabilized_after, target, installed_packages=installed_packages)
                if refreshed_match is not None and refreshed_match.node is not None:
                    history.append(NavigationState.REOBSERVE)
                    return self._activate_with_bounded_recovery(target, refreshed_stable, refreshed_match, installed_packages=installed_packages, expected_foreground_package=expected_foreground_package, history=history, total_scrolls=total_scrolls, direction=current_direction, progress=last_progress)
                history.append(NavigationState.REOBSERVE)
                return self._activate_with_bounded_recovery(target, stabilized_after, stabilized_match, installed_packages=installed_packages, expected_foreground_package=expected_foreground_package, history=history, total_scrolls=total_scrolls, direction=current_direction, progress=last_progress)
            after = stabilized_after
            progress = compare_snapshots(snapshot, after)
            last_progress = progress
            if progress.meaningful:
                no_progress = 0
            else:
                no_progress += 1
            if no_progress >= self.no_progress_before_reversal:
                current_direction = "up" if current_direction == "down" else "down"
                no_progress = 0
                scroll_distance_ratio = max(0.20, scroll_distance_ratio * 0.70)
            snapshot = after

        return self._result(target=target, state=NavigationState.FAILURE, history=history + [NavigationState.RECOVER], snapshot=snapshot, progress=last_progress, scroll_count=total_scrolls, direction=current_direction, message="Target was not reached within the bounded navigation budget.")
