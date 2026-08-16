"""Convert raw Android UI nodes into a compact agent-friendly state."""


def _meaningful(node):
    return bool(
        node.get("text")
        or node.get("content_description")
        or node.get("resource_id")
    )


def summarize_ui(nodes):
    """Return a compact representation while preserving actionable details."""
    if not isinstance(nodes, list):
        return {"visible_text": [], "interactive": [], "scrollable": [], "packages": []}

    visible_text = []
    interactive = []
    scrollable = []
    packages = []
    seen_text = set()
    seen_interactive = set()
    seen_packages = set()

    for node in nodes:
        text = (node.get("text") or "").strip()
        desc = (node.get("content_description") or "").strip()
        resource_id = (node.get("resource_id") or "").strip()
        package = (node.get("package") or "").strip()
        label = text or desc or resource_id

        if package and package not in seen_packages:
            seen_packages.add(package)
            packages.append(package)

        if text and text not in seen_text:
            seen_text.add(text)
            visible_text.append(text)

        if label and (node.get("clickable") or node.get("focusable")):
            key = (label, resource_id)
            if key not in seen_interactive:
                seen_interactive.add(key)
                interactive.append({
                    "label": label,
                    "text": text,
                    "content_description": desc,
                    "resource_id": resource_id,
                    "class": node.get("class", ""),
                    "bounds": node.get("bounds", ""),
                    "enabled": bool(node.get("enabled", False)),
                })

        if node.get("scrollable"):
            scrollable.append({
                "class": node.get("class", ""),
                "resource_id": resource_id,
                "bounds": node.get("bounds", ""),
            })

    return {
        "visible_text": visible_text,
        "interactive": interactive,
        "scrollable": scrollable,
        "packages": packages,
        "node_count": len(nodes),
    }


def format_ui_summary(state):
    """Create a concise terminal/LLM-readable UI summary."""
    lines = [f"UI nodes: {state.get('node_count', 0)}"]

    packages = state.get("packages") or []
    if packages:
        lines.append("Packages: " + ", ".join(packages[:5]))

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
