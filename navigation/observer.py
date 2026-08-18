"""Observation adapter for Nova's adaptive navigation engine."""

from __future__ import annotations

import time
from typing import Optional

from tools.observe_android import observe_android

from .state import ObservationQuality, ScreenSnapshot, snapshot_from_observation


DEFAULT_SETTLE_SECONDS = 0.25
DEFAULT_RETRIES = 2


def _has_navigation_state(snapshot: ScreenSnapshot) -> bool:
    """Require actual UI hierarchy information before calling a snapshot valid."""
    return bool(
        snapshot.visible_nodes
        or snapshot.actionable_nodes
        or snapshot.visible_text
        or snapshot.scrollable_regions
    )


def observe_screen(
    previous: Optional[ScreenSnapshot] = None,
    *,
    include_nodes: bool = True,
    retries: int = DEFAULT_RETRIES,
    settle_seconds: float = DEFAULT_SETTLE_SECONDS,
) -> ScreenSnapshot:
    """Capture a live screen without letting an empty/transient dump steer navigation.

    Foreground-package information alone is insufficient for navigation because
    Android can briefly report the package while accessibility content is empty
    or stale during a transition.
    """
    attempts = max(1, int(retries))
    last_snapshot: Optional[ScreenSnapshot] = None

    for attempt in range(attempts):
        observed = observe_android(include_nodes=include_nodes)
        snapshot = snapshot_from_observation(observed)
        last_snapshot = snapshot

        if snapshot.valid and _has_navigation_state(snapshot):
            return snapshot

        if snapshot.valid:
            snapshot = ScreenSnapshot(
                foreground_package=snapshot.foreground_package,
                visible_nodes=snapshot.visible_nodes,
                actionable_nodes=snapshot.actionable_nodes,
                scrollable_regions=snapshot.scrollable_regions,
                visible_text=snapshot.visible_text,
                timestamp=snapshot.timestamp,
                observation_quality=ObservationQuality.TRANSIENT,
                message="Android reported a foreground package but no usable navigation UI; waiting for a stable hierarchy.",
            )
            last_snapshot = snapshot

        if attempt + 1 < attempts:
            time.sleep(max(0.0, float(settle_seconds)))

    if last_snapshot is None:
        return ScreenSnapshot(
            foreground_package="",
            observation_quality=ObservationQuality.FAILED,
            message="No Android observation was produced.",
        )

    if previous is not None and last_snapshot.failed:
        return ScreenSnapshot(
            foreground_package=last_snapshot.foreground_package or previous.foreground_package,
            visible_nodes=previous.visible_nodes,
            actionable_nodes=previous.actionable_nodes,
            scrollable_regions=previous.scrollable_regions,
            visible_text=previous.visible_text,
            timestamp=last_snapshot.timestamp,
            observation_quality=ObservationQuality.TRANSIENT,
            message="Current observation failed; retaining the last valid snapshot for recovery.",
        )

    return last_snapshot
