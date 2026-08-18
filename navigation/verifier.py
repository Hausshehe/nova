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


def _bounds_tuple(value: str):
    import re
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", str(value or "").strip())
    if not match:
        return None
    return tuple(map(int, match.groups()))


def _target_transitioned(before: ScreenSnapshot, after: ScreenSnapshot, expected_target: str) -> tuple[bool, bool]:
    """Require destination-aware semantic evidence for the expected target.

    Seeing the source target disappear is not enough: an unrelated screen can
    also make the source label disappear. A disappearance is accepted only
    when the resulting screen provides a semantic successor for that target or
    the foreground package actually changes.
    """
    before_match = resolve_target(before, expected_target)
    after_match = resolve_target(after, expected_target)

    before_found = before_match.resolution is Resolution.FOUND and before_match.node is not None
    after_found = after_match.resolution is Resolution.FOUND and after_match.node is not None

    # A target appearing on a destination/result screen is valid evidence only
    # when it was not already the source target on the previous screen.
    if not before_found and after_found:
        return True, True

    # If the source target remains visible, it may still have transitioned if
    # its live bounds moved substantially (for example, an expanded destination
    # or a meaningful layout transition). Small accessibility jitter is ignored.
    if before_found and after_found:
        before_label = " ".join(str(before_match.label or "").split()).lower()
        after_label = " ".join(str(after_match.label or "").split()).lower()
        before_bounds = _bounds_tuple(before_match.node.get("bounds", ""))
        after_bounds = _bounds_tuple(after_match.node.get("bounds", ""))
        if before_bounds is None or after_bounds is None:
            return False, True
        motion = max(
            abs(before_bounds[0] - after_bounds[0]),
            abs(before_bounds[1] - after_bounds[1]),
            abs(before_bounds[2] - after_bounds[2]),
            abs(before_bounds[3] - after_bounds[3]),
        )
        return motion >= 40 or before_label != after_label, True

    # The source target disappeared. Treat it as a valid activation transition
    # only when the resulting semantic match changed to a different label or
    # the foreground package changed. This is intentionally not "disappearance
    # alone", which would accept arbitrary unrelated screen changes.
    if before_found and not after_found:
        if before.foreground_package != after.foreground_package:
            return True, False
        after_label = " ".join(str(after_match.label or "").split()).lower()
        if after_label and after_label != " ".join(str(before_match.label or "").split()).lower():
            return True, True
        return False, False

    return False, False


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

    With an expected target, meaningful UI change plus destination-aware target
    evidence is required. This prevents delayed scroll/layout changes or an
    unrelated screen from being mistaken for successful activation.
    """
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    last = before

    while time.monotonic() < deadline:
        current = observe_screen(previous=last, include_nodes=True, retries=1)
        last = current

        if current.observation_quality is not ObservationQuality.VALID:
            time.sleep(max(0.0, float(poll_seconds)))
            continue

        package_ok = not expected_foreground_package or current.foreground_package == expected_foreground_package
        meaningful = _meaningful_transition(before, current)
        target_ok = True
        target_resolved = False
        if expected_target:
            target_ok, target_resolved = _target_transitioned(before, current, expected_target)

        if package_ok and meaningful and (target_ok if expected_target else True):
            if expected_target:
                reason = "Expected foreground package is active and the target participated in a meaningful destination-aware live UI transition." if expected_foreground_package else "The target participated in a meaningful destination-aware live UI transition."
            elif expected_foreground_package:
                reason = "Expected foreground package is active."
            else:
                reason = "A meaningful live UI transition was verified."
            return VerificationResult(True, current, reason, target_resolved=target_resolved)

        time.sleep(max(0.0, float(poll_seconds)))

    if last is None:
        last = observe_screen(include_nodes=True, retries=1)

    return VerificationResult(
        False,
        last,
        "No verified target-consistent activation transition was observed within the bounded verification window.",
        target_resolved=False,
    )
