"""Observation adapter for Nova's adaptive navigation engine."""

from __future__ import annotations

import time
from typing import Optional

from tools.observe_android import observe_android

from .state import ObservationQuality, ScreenSnapshot, snapshot_from_observation


DEFAULT_SETTLE_SECONDS = 0.25
DEFAULT_RETRIES = 2


def observe_screen(
    previous: Optional[ScreenSnapshot] = None,
    *,
    include_nodes: bool = True,
    retries: int = DEFAULT_RETRIES,
    settle_seconds: float = DEFAULT_SETTLE_SECONDS,
) -> ScreenSnapshot:
    """Capture a live screen without allowing one bad observation to steer navigation.

    The existing Android observer remains responsible for bounded shell/UI-dump
    execution. This layer adds navigation-specific classification and a small
    settle/retry policy. A failed observation is never silently converted into
    a valid empty screen.
    """
    attempts = max(1, int(retries))
    last_snapshot: Optional[ScreenSnapshot] = None

    for attempt in range(attempts):
        observed = observe_android(include_nodes=include_nodes)
        snapshot = snapshot_from_observation(observed)
        last_snapshot = snapshot

        if snapshot.valid and snapshot.visible_nodes:
            return snapshot

        # An empty hierarchy can be a short-lived accessibility transition.
        # Do not let it immediately trigger scrolling or direction reversal.
        if snapshot.valid and not snapshot.visible_nodes:
            snapshot = ScreenSnapshot(
                foreground_package=snapshot.foreground_package,
                visible_nodes=snapshot.visible_nodes,
                actionable_nodes=snapshot.actionable_nodes,
                scrollable_regions=snapshot.scrollable_regions,
                visible_text=snapshot.visible_text,
                timestamp=snapshot.timestamp,
                observation_quality=ObservationQuality.TRANSIENT,
                message="Android returned an empty UI hierarchy; waiting for a stable snapshot.",
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
