"""Interact with a node selected from the current Android UI hierarchy."""

import re

from tools.android_root import run_root
from tools.observe_android import observe_android


def _parse_bounds(bounds):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    x1, y1, x2, y2 = map(int, match.groups())
    return x1, y1, x2, y2


def _score(node, selector):
    """Score a node only when it actually matches the supplied selector."""
    score = 0
    matched = False

    for key, value in selector.items():
        if value is None or value == "":
            continue

        actual = node.get(key, "")
        actual_s = str(actual).strip().lower()
        value_s = str(value).strip().lower()

        if actual_s == value_s:
            score += 100
            matched = True
        elif key in {"text", "content_description", "resource_id", "class", "package"} and value_s in actual_s:
            score += 25
            matched = True
        else:
            return 0

    if not matched:
        return 0

    if node.get("enabled"):
        score += 5
    if node.get("clickable"):
        score += 10
    return score


def click_node(selector=None, text=None, content_description=None,
               resource_id=None, class_name=None, package=None):
    """Find the best matching current UI node and tap its center."""
    selector = dict(selector or {})
    if text is not None:
        selector["text"] = text
    if content_description is not None:
        selector["content_description"] = content_description
    if resource_id is not None:
        selector["resource_id"] = resource_id
    if class_name is not None:
        selector["class"] = class_name
    if package is not None:
        selector["package"] = package

    if not selector:
        return {"success": False, "error": "A UI node selector is required"}

    # This tool needs the raw hierarchy internally; keep that payload out of
    # the normal LLM-facing observe_android result.
    observed = observe_android(include_nodes=True)
    if not observed.get("success"):
        return {"success": False, "error": observed.get("message", "UI observation failed")}

    candidates = []
    for node in observed.get("nodes", []):
        score = _score(node, selector)
        if score > 0:
            candidates.append((score, node))

    if not candidates:
        return {
            "success": False,
            "verified": False,
            "error": "No matching UI node found",
            "selector": selector,
        }

    candidates.sort(key=lambda item: item[0], reverse=True)
    score, node = candidates[0]
    bounds = _parse_bounds(node.get("bounds"))
    if not bounds:
        return {
            "success": False,
            "verified": False,
            "error": "Matching node has invalid bounds",
            "selector": selector,
        }

    x1, y1, x2, y2 = bounds
    x = (x1 + x2) // 2
    y = (y1 + y2) // 2

    result = run_root(f"input tap {x} {y}")
    if result.returncode != 0:
        return {
            "success": False,
            "verified": False,
            "selector": selector,
            "error": (result.stderr or result.stdout or "Tap failed").strip(),
        }

    return {
        "success": True,
        "verified": False,
        "selector": selector,
        "matched_label": (
            node.get("text")
            or node.get("content_description")
            or node.get("resource_id")
            or "matching node"
        ),
        "score": score,
        "tap": {"x": x, "y": y},
        "message": "Matching UI node tapped successfully.",
    }
