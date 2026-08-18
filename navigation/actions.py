"""Deterministic Android actions used by the navigation controller."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from tools.android_root import run_root


ACCESSIBILITY_CLICK_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class ActionResult:
    """Structured result of an Android interaction."""

    success: bool
    action: str
    message: str = ""
    bounds: str = ""


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _parse_bounds(bounds: str) -> Optional[Tuple[int, int, int, int]]:
    match = _BOUNDS_RE.fullmatch(str(bounds or "").strip())
    if not match:
        return None
    left, top, right, bottom = map(int, match.groups())
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _bounds_center(bounds: str) -> Optional[Tuple[int, int]]:
    parsed = _parse_bounds(bounds)
    if parsed is None:
        return None
    left, top, right, bottom = parsed
    return (left + right) // 2, (top + bottom) // 2


def _contains(outer: Tuple[int, int, int, int], inner: Tuple[int, int, int, int]) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def _semantic_label(node: Dict[str, Any]) -> str:
    return (
        str(node.get("text") or "").strip()
        or str(node.get("content_description") or "").strip()
        or str(node.get("resource_id") or "").strip()
    )


def _accessibility_click(label: str) -> Tuple[bool, str]:
    """Ask Nova's accessibility service to click a semantic live target."""
    label = " ".join(str(label or "").split())
    if not label:
        return False, "The target has no semantic label for accessibility activation."

    try:
        result = subprocess.run(
            [
                "am",
                "broadcast",
                "-n",
                "com.infoney.nova/.NovaClickReceiver",
                "-a",
                "com.infoney.nova.CLICK_ELEMENT",
                "--es",
                "target",
                label,
            ],
            capture_output=True,
            text=True,
            timeout=ACCESSIBILITY_CLICK_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Accessibility activation transport unavailable: {exc}"

    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode == 0 and re.search(r"result=1\b", output):
        return True, "Semantic target activated through the Accessibility Service."
    return False, output or "Accessibility Service did not report a successful semantic activation."


def activate_node(node: Optional[Dict[str, Any]]) -> ActionResult:
    """Activate a live semantic node, preferring Accessibility over root coordinates."""
    if not isinstance(node, dict):
        return ActionResult(False, "TAP", "No target node was supplied.")
    if not node.get("enabled", True):
        return ActionResult(False, "TAP", "Target node is disabled.")

    candidate = node
    if not node.get("clickable"):
        ancestor = node.get("actionable_ancestor")
        if isinstance(ancestor, dict) and ancestor.get("enabled", True):
            node_bounds = _parse_bounds(node.get("bounds", ""))
            ancestor_bounds = _parse_bounds(ancestor.get("bounds", ""))
            if node_bounds is None or ancestor_bounds is None:
                return ActionResult(False, "TAP", "Target/actionable ancestor does not have valid live bounds.")
            if not _contains(ancestor_bounds, node_bounds):
                return ActionResult(False, "TAP", "Actionable ancestor bounds do not contain the target bounds.")
            candidate = ancestor

    bounds = str(candidate.get("bounds", ""))
    center = _bounds_center(bounds)
    if center is None:
        return ActionResult(False, "TAP", "Target has no valid live bounds.", bounds)

    label = _semantic_label(node)
    if label:
        accessibility_success, accessibility_message = _accessibility_click(label)
        if accessibility_success:
            return ActionResult(True, "TAP", accessibility_message, bounds)

    # Fallback remains coordinate-free at the decision layer: coordinates are
    # calculated only from the current live target/actionable-ancestor bounds.
    time.sleep(0.12)
    x, y = center
    result = run_root(f"input tap {x} {y}")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Tap failed").strip()
        return ActionResult(False, "TAP", message, bounds)

    return ActionResult(True, "TAP", "Live target bounds activated through the bounded root fallback.", bounds)


def scroll(snapshot, direction: str, *, distance_ratio: float = 0.35) -> ActionResult:
    """Scroll a live region by an adaptive fraction of its observed height.

    No screen coordinates are fixed here. The gesture is derived entirely
    from the currently observed scrollable region, and callers can reduce the
    distance during recovery when a previous gesture moved too far or failed.
    """
    regions = [item for item in snapshot.scrollable_regions if isinstance(item, dict)]
    if not regions:
        return ActionResult(False, "SCROLL", "No live scrollable region is available.")

    def area(item: Dict[str, Any]) -> int:
        parsed = _parse_bounds(item.get("bounds", ""))
        if parsed is None:
            return 0
        left, top, right, bottom = parsed
        return (right - left) * (bottom - top)

    region = max(regions, key=area)
    parsed = _parse_bounds(region.get("bounds", ""))
    if parsed is None:
        return ActionResult(False, "SCROLL", "Scrollable region has invalid live bounds.")

    left, top, right, bottom = parsed
    width = right - left
    height = bottom - top
    if width < 80 or height < 160:
        return ActionResult(False, "SCROLL", "Scrollable region is too small for a safe gesture.")

    ratio = max(0.20, min(float(distance_ratio), 0.60))
    x = (left + right) // 2
    center_y = (top + bottom) // 2
    distance = max(40, int(height * ratio))
    direction = str(direction or "down").lower().strip()
    if direction == "down":
        start_y = center_y + distance // 2
        end_y = center_y - distance // 2
    elif direction == "up":
        start_y = center_y - distance // 2
        end_y = center_y + distance // 2
    else:
        return ActionResult(False, "SCROLL", f"Unsupported scroll direction: {direction}.")

    start_y = max(top + 10, min(bottom - 10, start_y))
    end_y = max(top + 10, min(bottom - 10, end_y))
    if start_y == end_y:
        return ActionResult(False, "SCROLL", "Computed scroll gesture has no movement.", region.get("bounds", ""))

    duration_ms = max(420, min(750, 300 + int(distance * 0.80)))
    result = run_root(f"/system/bin/input swipe {x} {start_y} {x} {end_y} {duration_ms}")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Scroll failed").strip()
        return ActionResult(False, "SCROLL", message, region.get("bounds", ""))

    return ActionResult(True, "SCROLL", f"Live scrollable region swiped using {ratio:.2f} of its observed height over {duration_ms}ms.", region.get("bounds", ""))
