"""Compatibility adapter for Nova's adaptive navigation engine.

The production navigation implementation now lives in ``navigation``.
This module preserves the existing tool name/result shape so older callers can
migrate without keeping the fragile legacy navigation state machine alive.
"""

from __future__ import annotations

from navigation.controller import NavigationController
from navigation.goal_parser import parse_open_path
from navigation.path import OpenPathNavigator


def navigate_android_to(target, max_scrolls=8, direction="down"):
    """Navigate through the live Android UI using checkpoint-aware navigation.

    No package lookup, fixed coordinate, app-specific handoff, or direct app
    launch is performed here. Installed-app launching remains the responsibility
    of the dedicated app-launch primitive and exact foreground verification.
    """
    targets = parse_open_path(target)
    if not targets:
        return {
            "success": False,
            "verified": False,
            "message": "Target cannot be empty.",
        }

    try:
        budget = max(0, min(int(max_scrolls), 20))
    except (TypeError, ValueError):
        budget = 8

    initial_direction = str(direction or "down").strip().lower()
    if initial_direction not in {"up", "down"}:
        initial_direction = "down"

    controller = NavigationController(
        max_scrolls=budget,
        settle_seconds=0.25,
    )
    navigator = OpenPathNavigator(
        controller,
        initial_direction=initial_direction,
    )
    result = navigator.navigate("open " + " and open ".join(targets))

    snapshot = None
    if navigator.checkpoints.latest is not None:
        snapshot = navigator.checkpoints.latest.snapshot

    return {
        "success": result.success,
        "verified": result.verified,
        "target": target,
        "completed_targets": result.completed_targets,
        "failed_target": result.failed_target,
        "checkpoints": result.checkpoints,
        "resumed_from_checkpoint": result.resumed_from_checkpoint,
        "foreground_package": snapshot.foreground_package if snapshot else "",
        "message": result.message,
    }
