"""Post-action verification for Nova's adaptive navigation engine."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from .observer import observe_screen
from .state import ObservationQuality, ScreenSnapshot


@dataclass(frozen=True)
class VerificationResult:
    success: bool
    snapshot: ScreenSnapshot
    reason: str


def verify_transition(
    before: Optional[ScreenSnapshot],
    *,
    expected_foreground_package: Optional[str] = None,
    timeout_seconds: float = 3.0,
    poll_seconds: float = 0.25,
) -> VerificationResult:
    """Wait for and verify a meaningful post-action UI transition."""
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    last = before

    while time.monotonic() < deadline:
        current = observe_screen(previous=last, include_nodes=True, retries=1)
        last = current

        if current.observation_quality is ObservationQuality.TRANSIENT:
            time.sleep(max(0.0, float(poll_seconds)))
            continue
        if current.observation_quality is ObservationQuality.FAILED:
            time.sleep(max(0.0, float(poll_seconds)))
            continue

        if expected_foreground_package:
            if current.foreground_package == expected_foreground_package:
                return VerificationResult(True, current, "Expected foreground package is active.")
        elif before is None or current.semantic_signature() != before.semantic_signature():
            return VerificationResult(True, current, "The live UI changed after the action.")

        time.sleep(max(0.0, float(poll_seconds)))

    if last is None:
        last = observe_screen(include_nodes=True, retries=1)

    return VerificationResult(
        False,
        last,
        "No verified foreground/package change or meaningful UI transition was observed within the bounded verification window.",
    )
