"""Deterministic Android actions used by the navigation controller."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from tools.android_root import run_root

from .state import ScreenSnapshot


@dataclass(frozen=True)
class ActionResult:
    """Structured result of an Android interaction."""

    success: bool
    action: str
    message: str = ""
    bounds: str = ""


def _bounds_center(bounds: str) -> Optional[Tuple[int, int]]:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", str(bounds or ""))
    if not match:
        return None
    left, top, right, bottom = map(int, match.groups())
    return (left + right) // 2, (top + bottom) // 2


def activate_node(node: Optional[Dict[str, Any]]) -> ActionResult:
    """Tap the live node or its nearest actionable ancestor using live bounds."""
    if not isinstance(node, dict):
        return ActionResult(False, "TAP", "No target node was supplied.")
    if not node.get("enabled", True):
        return ActionResult(False, "TAP", "Target node is disabled.")

    candidate = node
    if not node.get("clickable"):
        ancestor = node.get("actionable_ancestor")
        if isinstance(ancestor, dict) and ancestor.get("enabled", True):
            candidate = ancestor

    bounds = str(candidate.get("bounds", ""))
    center = _bounds_center(bounds)
    if center is None:
        return ActionResult(False, "TAP", "Target has no valid live bounds.", bounds)

    x, y = center
    result = run_root(f"input tap {x} {y}")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Tap failed").strip()
        return ActionResult(False, "TAP", message, bounds)

    return ActionResult(True, "TAP", "Live target bounds activated successfully.", bounds)


def scroll(snapshot: ScreenSnapshot, direction: str) -> ActionResult:
    """Scroll the largest live scrollable region in the requested direction."""
    regions = [item for item in snapshot.scrollable_regions if isinstance(item, dict)]
    if not regions:
        return ActionResult(False, "SCROLL", "No live scrollable region is available.")

    def area(item: Dict[str, Any]) -> int:
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", item.get("bounds", ""))
        if not match:
            return 0
        left, top, right, bottom = map(int, match.groups())
        return max(0, right - left) * max(0, bottom - top)

    region = max(regions, key=area)
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", region.get("bounds", ""))
    if not match:
        return ActionResult(False, "SCROLL", "Scrollable region has invalid live bounds.")

    left, top, right, bottom = map(int, match.groups())
    width = right - left
    height = bottom - top
    if width < 80 or height < 160:
        return ActionResult(False, "SCROLL", "Scrollable region is too small for a safe gesture.")

    x = (left + right) // 2
    upper = top + max(10, int(height * 0.25))
    lower = top + min(height - 10, int(height * 0.75))
    direction = str(direction or "down").lower().strip()
    if direction == "up":
        start_y, end_y = upper, lower
    elif direction == "down":
        start_y, end_y = lower, upper
    else:
        return ActionResult(False, "SCROLL", f"Unsupported scroll direction: {direction}.")

    result = run_root(f"/system/bin/input swipe {x} {start_y} {x} {end_y} 350")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Scroll failed").strip()
        return ActionResult(False, "SCROLL", message, region.get("bounds", ""))

    return ActionResult(True, "SCROLL", "Live scrollable region swiped successfully.", region.get("bounds", ""))
