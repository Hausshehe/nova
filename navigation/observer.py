"""Observation adapter for Nova's adaptive navigation engine."""

from __future__ import annotations

import time
from typing import Optional

from tools.accessibility_snapshot import read_accessibility_snapshot
from tools.observe_android import observe_android

from .state import ObservationQuality, ScreenSnapshot, snapshot_from_observation


DEFAULT_SETTLE_SECONDS = 0.25
DEFAULT_RETRIES = 2
ACCESSIBILITY_MAX_AGE_SECONDS = 2.0


def _has_navigation_state(snapshot: ScreenSnapshot) -> bool:
    """Require actual UI hierarchy information before calling a snapshot valid."""
    return bool(
        snapshot.visible_nodes
        or snapshot.actionable_nodes
        or snapshot.visible_text
        or snapshot.scrollable_regions
    )


def _accessibility_observation() -> Optional[dict]:
    """Convert a fresh service snapshot to the existing observer contract."""
    data = read_accessibility_snapshot(max_age_seconds=ACCESSIBILITY_MAX_AGE_SECONDS)
    if data is None:
        return None

    nodes = data.get("nodes") or []
    visible_text = []
    interactive = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for value in (node.get("text"), node.get("content_description")):
            value = str(value or "").strip()
            if value and value not in visible_text:
                visible_text.append(value)
        if node.get("clickable") and node.get("enabled"):
            interactive.append(node)

    scrollable = [
        {"bounds": str(bounds)}
        for bounds in (data.get("scrollable") or [])
        if str(bounds).strip()
    ]

    return {
        "success": True,
        "verified": True,
        "foreground_package": str(data.get("foreground_package", "")),
        "nodes": nodes,
        "state": {
            "visible_text": visible_text,
            "interactive": interactive,
            "scrollable": scrollable,
        },
        "message": "Fresh accessibility-service snapshot captured successfully.",
    }


def observe_screen(
    previous: Optional[ScreenSnapshot] = None,
    *,
    include_nodes: bool = True,
    retries: int = DEFAULT_RETRIES,
    settle_seconds: float = DEFAULT_SETTLE_SECONDS,
) -> ScreenSnapshot:
    """Capture a live screen using accessibility first and UIAutomator as fallback.

    A failed fresh observation is never represented by copying the previous live
    hierarchy. That distinction is important after actions: retaining old nodes
    can make the controller believe that the UI is unchanged when the observation
    itself simply failed.
    """
    attempts = max(1, int(retries))
    last_snapshot: Optional[ScreenSnapshot] = None

    for attempt in range(attempts):
        observed = _accessibility_observation()
        if observed is None:
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

    return last_snapshot
