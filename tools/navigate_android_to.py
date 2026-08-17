"""Generic semantic Android navigation helper for Nova.

This tool is deliberately app-agnostic. It searches the current UI hierarchy
for a human target, scrolls a real scrollable UI when the target is off-screen,
and activates the best current semantic match. Nova still chooses the target;
the tool never contains app-specific screen names or coordinates.
"""

import re
from difflib import SequenceMatcher

from tools.android_root import run_root
from tools.click_node import click_node
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


def _scroll(direction):
    if direction == "up":
        command = "/system/bin/input swipe 540 300 540 700 350"
    else:
        command = "/system/bin/input swipe 540 700 540 300 350"
    result = run_root(command)
    return result.returncode == 0


def navigate_android_to(target, max_scrolls=5, direction="down"):
    """Find and activate a human-named UI target using current semantic state.

    The helper first checks the current hierarchy. If the target is not visible
    but a scrollable area exists, it scrolls and re-observes until the target is
    found or the bounded scroll budget is exhausted. It uses no app-specific
    names and no fixed screen coordinates in planner logic.
    """
    target = str(target or "").strip()
    if not target:
        return {"success": False, "verified": False, "message": "Target cannot be empty."}

    try:
        budget = max(0, min(int(max_scrolls), 12))
    except (TypeError, ValueError):
        budget = 5

    direction = str(direction or "down").strip().lower()
    if direction not in {"up", "down"}:
        direction = "down"

    scrolls = 0
    last_state = None

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

        last_state = observed
        match = _find_match(observed.get("nodes"), target)
        if match:
            score, node, label = match
            selector = {}
            for key in ("text", "content_description", "resource_id", "class", "package"):
                value = node.get(key)
                if value:
                    selector[key] = value

            click_result = click_node(selector=selector)
            if click_result.get("success"):
                verification = observe_android(include_nodes=False)
                return {
                    "success": True,
                    "verified": bool(verification.get("success")),
                    "target": target,
                    "matched_label": label,
                    "match_score": round(score, 1),
                    "scrolls": scrolls,
                    "foreground_package": verification.get("foreground_package", ""),
                    "message": "Target found and activated using the current UI hierarchy.",
                }

            return {
                "success": False,
                "verified": False,
                "target": target,
                "matched_label": label,
                "scrolls": scrolls,
                "message": click_result.get("error") or click_result.get("message", "Target could not be activated."),
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
        "foreground_package": (last_state or {}).get("foreground_package", ""),
        "message": "Target was not visible after the bounded semantic search; Nova can choose another generic route.",
    }
