"""Deterministic Android actions used by the navigation controller."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


ACCESSIBILITY_CLICK_TIMEOUT_SECONDS = 5.0
ACCESSIBILITY_SCROLL_TIMEOUT_SECONDS = 5.0


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


def _accessibility_broadcast(action: str, *, target: str = "", direction: str = "") -> Tuple[bool, str]:
    """Send one bounded semantic command to Nova's Accessibility Service."""
    command = [
        "am",
        "broadcast",
        "-n",
        "com.infoney.nova/.NovaClickReceiver",
        "-a",
        action,
    ]
    if target:
        command.extend(["--es", "target", " ".join(str(target).split())])
    if direction:
        command.extend(["--es", "direction", direction])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=(
                ACCESSIBILITY_SCROLL_TIMEOUT_SECONDS
                if "SCROLL" in action
                else ACCESSIBILITY_CLICK_TIMEOUT_SECONDS
            ),
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Accessibility command transport unavailable: {exc}"

    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode == 0 and re.search(r"result=1\b", output):
        return True, output or "Accessibility command completed successfully."
    return False, output or "Accessibility Service did not report success."


def _accessibility_click(label: str) -> Tuple[bool, str]:
    """Ask Nova's Accessibility Service to click a semantic live target."""
    label = " ".join(str(label or "").split())
    if not label:
        return False, "The target has no semantic label for accessibility activation."
    return _accessibility_broadcast("com.infoney.nova.CLICK_ELEMENT", target=label)


def activate_node(node: Optional[Dict[str, Any]]) -> ActionResult:
    """Activate a live semantic node exclusively through Accessibility Service."""
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
    if _bounds_center(bounds) is None:
        return ActionResult(False, "TAP", "Target has no valid live bounds.", bounds)

    label = _semantic_label(node)
    if not label:
        return ActionResult(False, "TAP", "The target has no semantic label for accessibility activation.", bounds)

    success, message = _accessibility_click(label)
    if success:
        return ActionResult(True, "TAP", "Semantic target activated through the Accessibility Service.", bounds)
    return ActionResult(False, "TAP", message, bounds)


def _accessibility_scroll(direction: str) -> Tuple[bool, str]:
    direction = str(direction or "down").strip().lower()
    if direction not in {"down", "up"}:
        return False, f"Unsupported scroll direction: {direction}."
    return _accessibility_broadcast(
        "com.infoney.nova.SCROLL_WINDOW",
        direction=direction,
    )


def scroll(snapshot, direction: str, *, distance_ratio: float = 0.35) -> ActionResult:
    """Scroll the currently observed live region through Accessibility Service.

    The Python controller uses the observed region only to validate that a
    scroll is safe. The actual gesture is semantic: the Accessibility Service
    performs ACTION_SCROLL_FORWARD/BACKWARD on the live scroll container.
    This avoids privileged input commands, Magisk prompts, and coordinate
    gestures that can visibly blink or briefly stall the device.
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
        return ActionResult(False, "SCROLL", "Scrollable region is too small for a safe gesture.", region.get("bounds", ""))

    success, message = _accessibility_scroll(direction)
    if success:
        return ActionResult(
            True,
            "SCROLL",
            "Live scrollable region advanced through the Accessibility Service.",
            region.get("bounds", ""),
        )
    return ActionResult(False, "SCROLL", message, region.get("bounds", ""))
