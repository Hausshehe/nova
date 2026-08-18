"""Generic progress measurement for adaptive Android scrolling."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Tuple

from .state import ObservationQuality, ScreenSnapshot


@dataclass(frozen=True)
class Progress:
    changed: bool
    meaningful: bool
    new_text: Tuple[str, ...] = ()
    lost_text: Tuple[str, ...] = ()
    reason: str = ""


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _node_key(node: Dict[str, object]) -> str:
    return "|".join(
        (
            str(node.get("text", "")).strip().lower(),
            str(node.get("content_description", "")).strip().lower(),
            str(node.get("resource_id", "")).strip().lower(),
        )
    )


def _bounds(node: Dict[str, object]) -> Tuple[int, int, int, int] | None:
    match = _BOUNDS_RE.fullmatch(str(node.get("bounds", "")).strip())
    if not match:
        return None
    return tuple(int(value) for value in match.groups())


def _position_shift(before: ScreenSnapshot, after: ScreenSnapshot) -> bool:
    """Detect substantial movement of stable nodes, not merely tree reordering."""
    before_nodes = {
        _node_key(node): _bounds(node)
        for node in before.visible_nodes
        if isinstance(node, dict) and _bounds(node) is not None
    }
    after_nodes = {
        _node_key(node): _bounds(node)
        for node in after.visible_nodes
        if isinstance(node, dict) and _bounds(node) is not None
    }
    common = set(before_nodes) & set(after_nodes)
    if not common:
        return False

    moved = 0
    large_move = False
    for key in common:
        old = before_nodes[key]
        new = after_nodes[key]
        if old is None or new is None:
            continue
        dx = abs(((new[0] + new[2]) - (old[0] + old[2])) / 2)
        dy = abs(((new[1] + new[3]) - (old[1] + old[3])) / 2)
        if dx >= 20 or dy >= 20:
            moved += 1
        if dx >= 80 or dy >= 80:
            large_move = True

    return moved >= 2 or large_move


def compare_snapshots(before: ScreenSnapshot, after: ScreenSnapshot) -> Progress:
    """Determine whether a scroll produced evidence of meaningful UI progress."""
    if before.observation_quality is not ObservationQuality.VALID:
        return Progress(False, False, reason="Previous snapshot was not valid.")
    if after.observation_quality is not ObservationQuality.VALID:
        return Progress(False, False, reason="Current snapshot was not valid.")

    before_text = {text.strip().lower() for text in before.visible_text if text.strip()}
    after_text = {text.strip().lower() for text in after.visible_text if text.strip()}
    new_text = tuple(sorted(after_text - before_text))
    lost_text = tuple(sorted(before_text - after_text))
    package_changed = before.foreground_package != after.foreground_package
    moved_nodes = _position_shift(before, after)

    meaningful = bool(new_text or lost_text or package_changed or moved_nodes)

    if package_changed:
        reason = "Foreground package changed."
    elif new_text or lost_text:
        reason = "Visible semantic text changed."
    elif moved_nodes:
        reason = "Stable UI nodes moved substantially."
    else:
        reason = "No meaningful UI progress detected."

    return Progress(
        changed=meaningful,
        meaningful=meaningful,
        new_text=new_text,
        lost_text=lost_text,
        reason=reason,
    )
