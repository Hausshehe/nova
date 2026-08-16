"""Build compact, semantic Android UI state for Nova's adaptive reasoning."""

import re


_TEXT_FIELDS = ("text", "content_description", "resource_id")


def _meaningful(node):
    return any((node.get(field) or "").strip() for field in _TEXT_FIELDS)


def _bounds_center(bounds):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    left, top, right, bottom = map(int, match.groups())
    return {"x": (left + right) // 2, "y": (top + bottom) // 2}


def _label(node):
    return (
        (node.get("text") or "").strip()
        or (node.get("content_description") or "").strip()
        or (node.get("resource_id") or "").strip()
    )


def _node_key(node):
    return (
        node.get("text", ""),
        node.get("content_description", ""),
        node.get("resource_id", ""),
        node.get("class", ""),
        node.get("package", ""),
        node.get("bounds", ""),
    )


def summarize_ui(nodes):
    """Return compact state while retaining semantic details needed for planning."""
    if not isinstance(nodes, list):
        return {
            "visible_text": [],
            "interactive": [],
            "scrollable": [],
            "packages": [],
            "node_count": 0,
        }

    visible_text = []
    interactive = []
    scrollable = []
    packages = []
    seen_text = set()
    seen_interactive = set()
    seen_scrollable = set()
    seen_packages = set()

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue

        text = (node.get("text") or "").strip()
        desc = (node.get("content_description") or "").strip()
        resource_id = (node.get("resource_id") or "").strip()
        package = (node.get("package") or "").strip()
        class_name = (node.get("class") or "").strip()
        bounds = (node.get("bounds") or "").strip()
        label = _label(node)

        if package and package not in seen_packages:
            seen_packages.add(package)
            packages.append(package)

        if text and text not in seen_text:
            seen_text.add(text)
            visible_text.append(text)

        is_interactive = bool(
            node.get("clickable")
            or node.get("focusable")
            or node.get("checked")
        )
        if label and is_interactive:
            key = (label, resource_id, bounds)
            if key not in seen_interactive:
                seen_interactive.add(key)
                interactive.append({
                    "index": index,
                    "label": label,
                    "text": text,
                    "content_description": desc,
                    "resource_id": resource_id,
                    "class": class_name,
                    "package": package,
                    "bounds": bounds,
                    "center": _bounds_center(bounds),
                    "clickable": bool(node.get("clickable")),
                    "focusable": bool(node.get("focusable")),
                    "enabled": bool(node.get("enabled")),
                    "selected": bool(node.get("selected")),
                    "checked": bool(node.get("checked")),
                })

        if node.get("scrollable"):
            key = (class_name, resource_id, bounds)
            if key not in seen_scrollable:
                seen_scrollable.add(key)
                scrollable.append({
                    "index": index,
                    "class": class_name,
                    "resource_id": resource_id,
                    "package": package,
                    "bounds": bounds,
                    "center": _bounds_center(bounds),
                })

    return {
        "visible_text": visible_text,
        "interactive": interactive,
        "scrollable": scrollable,
        "packages": packages,
        "node_count": len(nodes),
    }


def format_ui_summary(state):
    """Create concise terminal output without discarding the structured state."""
    lines = [f"UI nodes: {state.get('node_count', 0)}"]

    packages = state.get("packages") or []
    if packages:
        lines.append("Packages: " + ", ".join(packages[:8]))

    text = state.get("visible_text") or []
    if text:
        lines.append("Visible text: " + " | ".join(text[:40]))

    interactive = state.get("interactive") or []
    if interactive:
        labels = [item["label"] for item in interactive[:30]]
        lines.append("Interactive: " + " | ".join(labels))

    scrollable = state.get("scrollable") or []
    if scrollable:
        lines.append(f"Scrollable areas: {len(scrollable)}")

    return "\n".join(lines)
