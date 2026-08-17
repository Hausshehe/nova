"""Generic semantic Android navigation helper for Nova.

This tool is deliberately app-agnostic. It searches the current UI hierarchy
for a human target, scrolls a real scrollable UI when the target is off-screen,
and activates the best current semantic match. Nova still chooses the target;
the tool never contains app-specific screen names or planner coordinates.
"""

import re
from difflib import SequenceMatcher

from tools.android_root import run_root
from tools.observe_android import observe_android


def _label(node):
    return (
        (node.get("text") or "").strip()
        or (node.get("content_description") or "").strip()
        or (node.get("resource_id") or "").strip()
    )


def _words(value):
    return set(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _score(label, target):
    label_n = " ".join(str(label or "").lower().split())
    target_n = " ".join(str(target or "").lower().split())
    if not label_n or not target_n:
        return 0.0
    if label_n == target_n:
        return 100.0
    if target_n in label_n:
        return 90.0

    target_words = _words(target_n)
    label_words = _words(label_n)
    if target_words:
        overlap = len(target_words & label_words) / len(target_words)
        if overlap == 1.0:
            return 85.0
        if overlap >= 0.5:
            return 60.0 + overlap * 20.0

    return SequenceMatcher(None, target_n, label_n).ratio() * 50.0


def _find_match(nodes, target):
    candidates = []
    for node in nodes or []:
        if not isinstance(node, dict) or not node.get("enabled", True):
            continue
        label = _label(node)
        score = _score(label, target)
        if score >= 50.0:
            candidates.append((score, node, label))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0]


def _bounds_center(bounds):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    x1, y1, x2, y2 = map(int, match.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def _activate(node):
    center = _bounds_center(node.get("bounds", ""))
    if center is None:
        return False, "Matching node has invalid bounds."
    x, y = center
    result = run_root(f"input tap {x} {y}")
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "Tap failed").strip()
    return True, ""


def _scroll(direction):
    if direction == "up":
        command = "/system/bin/input swipe 540 300 540 700 350"
    else:
        command = "/system/bin/input swipe 540 700 540 300 350"
    result = run_root(command)
    return result.returncode == 0


def navigate_android_to(target, max_scrolls=5, direction="down"):
    """Find and activate a human-named UI target using current semantic state.

    The helper checks the live hierarchy, scrolls a currently scrollable UI when
    needed, re-observes after each scroll, and activates the best current match.
    It uses no app-specific names and no fixed coordinates in planner logic.
    """
    target = str(target or "").strip()
    if not target:
        return {"success": False, "verified": False, "message": "Target cannot be empty."}

    try:
        budget = max(0, min(int(max_scrolls), 8))
    except (TypeError, ValueError):
        budget = 5

    direction = str(direction or "down").strip().lower()
    if direction not in {"up", "down"}:
        direction = "down"

    scrolls = 0
    last_foreground = ""

    for attempt in range(budget + 1):
        observed = observe_android(include_nodes=True)
        if not observed.get("success"):
            return {
                "success": False,
                "verified": False,
                "target": target,
                "scrolls": scrolls,
                "message": observed.get("message", "UI observation failed."),
            }

        last_foreground = observed.get("foreground_package", "")
        match = _find_match(observed.get("nodes"), target)
        if match:
            score, node, label = match
            activated, error = _activate(node)
            if not activated:
                return {
                    "success": False,
                    "verified": False,
                    "target": target,
                    "matched_label": label,
                    "scrolls": scrolls,
                    "message": error,
                }

            # One verification observation is enough; the planner will receive
            # this compact result and can observe again if it needs more detail.
            verification = observe_android(include_nodes=False)
            return {
                "success": True,
                "verified": bool(verification.get("success")),
                "target": target,
                "matched_label": label,
                "match_score": round(score, 1),
                "scrolls": scrolls,
                "foreground_package": verification.get("foreground_package", last_foreground),
                "message": "Target found and activated using the current UI hierarchy.",
            }

        state = observed.get("state") or {}
        if not state.get("scrollable") or attempt >= budget:
            break

        if not _scroll(direction):
            return {
                "success": False,
                "verified": False,
                "target": target,
                "scrolls": scrolls,
                "message": "The UI could not be scrolled.",
            }
        scrolls += 1

    return {
        "success": False,
        "verified": True,
        "target": target,
        "scrolls": scrolls,
        "foreground_package": last_foreground,
        "message": "Target was not visible after the bounded semantic search; Nova can choose another generic route.",
    }
