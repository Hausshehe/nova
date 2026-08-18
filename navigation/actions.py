"""Deterministic Android actions used by the navigation controller."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


ACCESSIBILITY_CLICK_TIMEOUT_SECONDS = 3.0
ACCESSIBILITY_SCROLL_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class ActionResult:
    """Structured result of an Android interaction."""

    success: bool
    action: str
    message: str = ""
    bounds: str = ""
    duration_ms: Optional[float] = None
    executor_returncode: Optional[int] = None


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


def _run_accessibility(command: list[str], *, timeout_seconds: float) -> tuple[bool, str, int, float]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        return False, f"Accessibility Service command timed out after {duration_ms}ms: {exc}", -1, duration_ms
    except (FileNotFoundError, OSError) as exc:
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        return False, f"Accessibility command transport unavailable: {exc}", -1, duration_ms

    duration_ms = round((time.monotonic() - started) * 1000, 1)
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode == 0 and re.search(r"result=1\b", output):
        return True, output or "Accessibility Service accepted the action.", result.returncode, duration_ms
    if result.returncode == 0 and re.search(r"result=0\b", output):
        return False, "Accessibility Service rejected the requested action; no root fallback was attempted.", result.returncode, duration_ms
    return False, output or "Accessibility Service did not report success.", result.returncode, duration_ms


def _accessibility_command(action: str, *, target: str = "", direction: str = "") -> list[str]:
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
    return command


def activate_node(node: Optional[Dict[str, Any]]) -> ActionResult:
    """Activate a validated semantic target through Nova's Accessibility Service."""
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

    label = (
        str(node.get("text") or "").strip()
        or str(node.get("content_description") or "").strip()
        or str(node.get("resource_id") or "").strip()
    )
    if not label:
        return ActionResult(False, "TAP", "The target has no semantic label for Accessibility activation.", bounds)

    success, message, returncode, duration_ms = _run_accessibility(
        _accessibility_command("com.infoney.nova.CLICK_ELEMENT", target=label),
        timeout_seconds=ACCESSIBILITY_CLICK_TIMEOUT_SECONDS,
    )
    return ActionResult(
        success,
        "TAP",
        "Semantic target activated through the Accessibility Service." if success else message,
        bounds,
        duration_ms=duration_ms,
        executor_returncode=returncode,
    )


def scroll(snapshot, direction: str, *, distance_ratio: float = 0.35) -> ActionResult:
    """Advance the live accessibility scroll container without root input injection."""
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
    bounds = str(region.get("bounds", ""))
    parsed = _parse_bounds(bounds)
    if parsed is None:
        return ActionResult(False, "SCROLL", "Scrollable region has invalid live bounds.", bounds)

    left, top, right, bottom = parsed
    if right - left < 80 or bottom - top < 160:
        return ActionResult(False, "SCROLL", "Scrollable region is too small for a safe action.", bounds)

    direction = str(direction or "down").strip().lower()
    if direction not in {"up", "down"}:
        return ActionResult(False, "SCROLL", f"Unsupported scroll direction: {direction}.", bounds)

    success, message, returncode, duration_ms = _run_accessibility(
        _accessibility_command("com.infoney.nova.SCROLL_WINDOW", direction=direction),
        timeout_seconds=ACCESSIBILITY_SCROLL_TIMEOUT_SECONDS,
    )
    return ActionResult(
        success,
        "SCROLL",
        "Live scrollable region advanced through the Accessibility Service." if success else message,
        bounds,
        duration_ms=duration_ms,
        executor_returncode=returncode,
    )
