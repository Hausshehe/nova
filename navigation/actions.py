"""Deterministic Android actions used by the navigation controller."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from tools.android_root import run_root


ACCESSIBILITY_CLICK_TIMEOUT_SECONDS = 5.0
ACCESSIBILITY_SCROLL_TIMEOUT_SECONDS = 5.0
ROOT_INPUT_TIMEOUT_SECONDS = 3.0


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
    """Send one bounded semantic command and expose its transport metadata."""
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
            return False, "Accessibility Service receiver rejected the requested action (result=0).", result.returncode, elapsed_ms
        return False, f"Accessibility Service receiver returned unexpected result={receiver_result}.", result.returncode, elapsed_ms

    return False, output or "Accessibility Service did not report a receiver result.", result.returncode, elapsed_ms


def _root_input(command: str) -> Tuple[bool, str, int, float]:
    """Execute one bounded privileged Android input command as a fallback."""
    started = time.monotonic()
    try:
        result = run_root(command, timeout=ROOT_INPUT_TIMEOUT_SECONDS)
    except Exception as exc:
        return False, f"Root input fallback unavailable: {exc}", -1, round((time.monotonic() - started) * 1000, 1)
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode == 0:
        return True, output or "Root input command completed.", result.returncode, elapsed_ms
    return False, output or f"Root input command failed with returncode={result.returncode}.", result.returncode, elapsed_ms


def _accessibility_click(label: str) -> Tuple[bool, str, int, float]:
    """Ask Nova's Accessibility Service to click a semantic live target."""
    label = " ".join(str(label or "").split())
    if not label:
        return False, "The target has no semantic label for accessibility activation.", -1, 0.0
    return _accessibility_broadcast("com.infoney.nova.CLICK_ELEMENT", target=label)


def activate_node(node: Optional[Dict[str, Any]]) -> ActionResult:
    """Activate a live semantic node with Accessibility first, root input second."""
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
    if not label:
        return ActionResult(False, "TAP", "The target has no semantic label for accessibility activation.", bounds)

    success, message, returncode, duration_ms = _accessibility_click(label)
    if success:
        return ActionResult(True, "TAP", "Accessibility activation accepted; higher-level verification is required.", bounds, duration_ms, returncode, message)

    x, y = center
    root_success, root_message, root_returncode, root_duration_ms = _root_input(f"input tap {x} {y}")
    if root_success:
        combined = f"Accessibility activation failed; rooted input tap fallback accepted at live bounds center ({x},{y}). {root_message}".strip()
        return ActionResult(True, "TAP", combined, bounds, round((duration_ms or 0.0) + root_duration_ms, 1), root_returncode, combined)

    combined = f"Accessibility activation failed: {message} Root tap fallback also failed: {root_message}"
    return ActionResult(False, "TAP", combined, bounds, round((duration_ms or 0.0) + root_duration_ms, 1), root_returncode, combined)


def _accessibility_scroll(direction: str) -> Tuple[bool, str, int, float]:
    direction = str(direction or "down").strip().lower()
    if direction not in {"down", "up"}:
        return False, f"Unsupported scroll direction: {direction}.", -1, 0.0
    return _accessibility_broadcast(
        "com.infoney.nova.SCROLL_WINDOW",
        direction=direction,
    )


def scroll(snapshot, direction: str, *, distance_ratio: float = 0.35) -> ActionResult:
    """Scroll the current live region with Accessibility first, root gesture second."""
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
    region_bounds = str(region.get("bounds", ""))
    parsed = _parse_bounds(region_bounds)
    if parsed is None:
        return ActionResult(False, "SCROLL", "Scrollable region has invalid live bounds.")

    left, top, right, bottom = parsed
    width = right - left
    height = bottom - top
    if width < 80 or height < 160:
        return ActionResult(False, "SCROLL", "Scrollable region is too small for a safe gesture.", region_bounds)

    direction = str(direction or "down").strip().lower()
    if direction not in {"down", "up"}:
        return ActionResult(False, "SCROLL", f"Unsupported scroll direction: {direction}.", region_bounds)

    success, message, returncode, duration_ms = _accessibility_scroll(direction)
    if success:
        return ActionResult(True, "SCROLL", "Accessibility scroll accepted; higher-level verification is required.", region_bounds, duration_ms, returncode, message)

    x = (left + right) // 2
    margin = max(40, int(height * 0.12))
    travel = max(120, int(height * max(0.20, min(float(distance_ratio), 0.60))))
    top_point = top + margin
    bottom_point = bottom - margin
    if bottom_point <= top_point + 120:
        return ActionResult(False, "SCROLL", f"Accessibility scroll failed: {message} Root gesture fallback is unsafe for this region.", region_bounds, duration_ms, returncode, message)

    if direction == "down":
        start_y = min(bottom_point, top_point + travel)
        end_y = max(top_point, start_y - travel)
    else:
        start_y = max(top_point, bottom_point - travel)
        end_y = min(bottom_point, start_y + travel)

    root_success, root_message, root_returncode, root_duration_ms = _root_input(
        f"input swipe {x} {start_y} {x} {end_y} 280"
    )
    if root_success:
        combined = f"Accessibility scroll failed; rooted swipe fallback accepted for live bounds {region_bounds}. {root_message}".strip()
        return ActionResult(True, "SCROLL", combined, region_bounds, round((duration_ms or 0.0) + root_duration_ms, 1), root_returncode, combined)

    combined = f"Accessibility scroll failed: {message} Root swipe fallback also failed: {root_message}"
    return ActionResult(False, "SCROLL", combined, region_bounds, round((duration_ms or 0.0) + root_duration_ms, 1), root_returncode, combined)
