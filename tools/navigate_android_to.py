"""Compatibility adapter for Nova's adaptive navigation engine.

The production navigation implementation now lives in ``navigation``.
This module preserves the existing tool name/result shape so older callers can
migrate without keeping the fragile legacy navigation state machine alive.
"""

from __future__ import annotations

from navigation.controller import NavigationController
from navigation.goal_parser import parse_open_path


def navigate_android_to(target, max_scrolls=8, direction="down"):
    """Navigate through the live Android UI using the rebuilt controller.

    No package lookup, fixed coordinate, app-specific handoff, or direct app
    launch is performed here. This adapter is intentionally UI-route-only:
    callers that need to launch an installed app should use the dedicated app
    launch primitive and verify the foreground package separately.
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
    completed = []
    total_scrolls = 0
    last_result = None

    for current_target in targets:
        result = controller.navigate_target(current_target)
        last_result = result
        total_scrolls += result.scroll_count

        if not result.success or not result.verified:
            snapshot = result.snapshot
            return {
                "success": False,
                "verified": bool(result.verified),
                "target": target,
                "completed_targets": completed,
                "failed_target": current_target,
                "scrolls": total_scrolls,
                "foreground_package": snapshot.foreground_package if snapshot else "",
                "message": result.message or f"Could not reach '{current_target}'.",
                "navigation_state": result.state.value,
                "history": [state.value for state in result.history],
            }

        completed.append({
            "target": current_target,
            "matched_label": result.match.label if result.match else "",
            "match_score": round(result.match.score, 1) if result.match else 0,
        })

    snapshot = last_result.snapshot if last_result else None
    return {
        "success": True,
        "verified": True,
        "target": target,
        "completed_targets": completed,
        "scrolls": total_scrolls,
        "foreground_package": snapshot.foreground_package if snapshot else "",
        "message": "All navigation targets were found and activated with the rebuilt adaptive navigation engine.",
        "navigation_state": last_result.state.value if last_result else "SUCCESS",
        "history": [state.value for state in last_result.history] if last_result else [],
    }
