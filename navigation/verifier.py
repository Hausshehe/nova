"""Post-action verification for Nova's adaptive navigation engine."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from .observer import observe_screen
from .state import ObservationQuality, Resolution, ScreenSnapshot
from .resolver import resolve_target


MIN_TEXT_CHANGE_RATIO = 0.20


@dataclass(frozen=True)
class VerificationResult:
    success: bool
    snapshot: ScreenSnapshot
    reason: str
    target_resolved: bool = False


def _text_change_ratio(before: ScreenSnapshot, after: ScreenSnapshot) -> float:
    before_text = {text.strip().lower() for text in before.visible_text if text.strip()}
    after_text = {text.strip().lower() for text in after.visible_text if text.strip()}
    if not before_text and not after_text:
        return 0.0
    union = before_text | after_text
    if not union:
        return 0.0
    return len(before_text ^ after_text) / len(union)


def _meaningful_transition(before: Optional[ScreenSnapshot], after: ScreenSnapshot) -> bool:
    if before is None:
        return bool(after.visible_nodes or after.visible_text)
    if before.foreground_package != after.foreground_package:
        return True
    return _text_change_ratio(before, after) >= MIN_TEXT_CHANGE_RATIO


def verify_transition(
    before: Optional[ScreenSnapshot],
    *,
    expected_foreground_package: Optional[str] = None,
    expected_target: Optional[str] = None,
    timeout_seconds: float = 3.0,
    poll_seconds: float = 0.25,
) -> VerificationResult:
    """Wait for and verify a meaningful post-action UI transition.

    A successful verification must come from a VALID observation. When the
    caller supplies an expected target, the target must also resolve on the
    resulting live hierarchy; a generic UI change is not enough.
    """
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    last = before

    while time.monotonic() < deadline:
        current = observe_screen(previous=last, include_nodes=True, retries=1)
        last = current

        if current.observation_quality is not ObservationQuality.VALID:
            time.sleep(max(0.0, float(poll_seconds)))
            continue

        package_ok = (
            not expected_foreground_package
            or current.foreground_package == expected_foreground_package
        )
        target_ok = True
        if expected_target:
            target_match = resolve_target(current, expected_target)
            target_ok = target_match.resolution is Resolution.FOUND and target_match.node is not None

        if package_ok and (target_ok if expected_target else _meaningful_transition(before, current)):
            reason = (
                "Expected foreground package is active and the target is visible."
                if expected_foreground_package and expected_target
                else "Expected foreground package is active."
                if expected_foreground_package
                else "Target is visible on the resulting live hierarchy."
                if expected_target
                else "A meaningful live UI transition was verified."
            )
            return VerificationResult(True, current, reason, target_resolved=bool(expected_target))

        time.sleep(max(0.0, float(poll_seconds)))

    if last is None:
        last = observe_screen(include_nodes=True, retries=1)

    return VerificationResult(
        False,
        last,
        "No verified foreground/package change or target-consistent semantic transition was observed within the bounded verification window.",
        target_resolved=False,
    )
