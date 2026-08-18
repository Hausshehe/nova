"""Deterministic Android actions used by the navigation controller."""

from __future__ import annotations

import re
import subprocess
import time
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
    duration_ms: Optional[float] = None
    executor_returncode: Optional[int] = None
    transport_output: str = ""


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_RECEIVER_RESULT_RE = re.compile(r"(?:Broadcast completed:\s*)?result=(-?\d+)\b")


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


def _accessibility_broadcast(action: str, *, target: str = "", direction: str = "") -> Tuple[bool, str, int, float]:
    """Send one bounded semantic command and expose its transport metadata.

    Android's ``am broadcast`` shell exit code is not the Accessibility receiver's
    result code. In particular, a receiver returning result=1 can make ``am`` exit
    with code 1. The receiver result is therefore the authoritative action result;
    the shell return code remains diagnostic metadata.
    """
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

    started = time.monotonic()
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
        return False, f"Accessibility Service command transport unavailable: {exc}", -1, round((time.monotonic() - started) * 1000, 1)

    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    match = _RECEIVER_RESULT_RE.search(output)

    if match:
        receiver_result = int(match.group(1))
        if receiver_result == 1:
            return True, output or "Accessibility Service receiver accepted the action.", result.returncode, elapsed_ms
        if receiver_result == 0:
            return False, "Accessibility Service receiver rejected the requested action (result=0); no root fallback was attempted.", result.returncode, elapsed_ms
        return False, f"Accessibility Service receiver returned unexpected result={receiver_result}.", result.returncode, elapsed_ms

    return False, output or "Accessibility Service did not report a receiver result.", result.returncode, elapsed_ms


def _accessibility_click(label: str) -> Tuple[bool, str, int, float]:
    """Ask Nova's Accessibility Service to click a semantic live target."""
    label = " ".join(str(label or "").split())
    if not label:
        return False, "The target has no semantic label for accessibility activation.", -1, 0.0
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

    success, message, returncode, duration_ms = _accessibility_click(label)
    if success:
        return ActionResult(True, "TAP", "Semantic target activated through the Accessibility Service.", bounds, duration_ms, returncode, message)
    return ActionResult(False, "TAP", message, bounds, duration_ms, returncode, message)


def _accessibility_scroll(direction: str) -> Tuple[bool, str, int, float]:
    direction = str(direction or "down").strip().lower()
    if direction not in {"down", "up"}:
        return False, f"Unsupported scroll direction: {direction}.", -1, 0.0
    return _accessibility_broadcast(
        "com.infoney.nova.SCROLL_WINDOW",
        direction=direction,
    )


def scroll(snapshot, direction: str, *, distance_ratio: float = 0.35) -> ActionResult:
    """Scroll the currently observed live region through Accessibility Service."""
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

    success, message, returncode, duration_ms = _accessibility_scroll(direction)
    if success:
        return ActionResult(True, "SCROLL", "Live scrollable region advanced through the Accessibility Service.", region.get("bounds", ""), duration_ms, returncode, message)
    return ActionResult(False, "SCROLL", message, region.get("bounds", ""), duration_ms, returncode, message)
