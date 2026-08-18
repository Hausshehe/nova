"""Observe Android UI and return compact state for Nova's reasoning.

The full node list can still be requested by internal UI tools, but the
normal LLM-facing result intentionally omits it to prevent huge provider
requests.
"""

import re
import time
import xml.etree.ElementTree as ET
from collections import Counter

from tools.android_root import run_root
from tools.android_ui import format_ui_summary, summarize_ui

DUMP_PATH = "/data/local/tmp/nova_ui.xml"
# Keep each observation bounded tightly enough that a slow Android dump cannot
# make a navigation step feel hung. Navigation-level retries classify a missed
# dump as transient and can safely request another observation.
OBSERVE_TIMEOUT_SECONDS = 6
OBSERVE_RETRIES = 2
OBSERVE_RETRY_DELAY = 0.2
FOREGROUND_RETRIES = 3
FOREGROUND_RETRY_DELAY = 0.15


def _foreground_package():
    """Return the package currently reported as the foreground/resumed app."""
    result = run_root(
        "dumpsys activity activities | grep -m 1 -E 'mResumedActivity|mCurrentFocus|mFocusedApp'",
        timeout=4,
    )
    if result.returncode != 0:
        return ""

    line = (result.stdout or "").strip()
    match = re.search(r"(?:u\d+\s+)?([A-Za-z0-9_.$]+)/(?:[A-Za-z0-9_.$]+)", line)
    return match.group(1) if match else ""


def _infer_foreground_from_nodes(nodes):
    """Infer the foreground package from the UI hierarchy as a fallback."""
    packages = [
        node.get("package", "").strip()
        for node in nodes
        if isinstance(node, dict) and node.get("package", "").strip()
    ]
    if not packages:
        return ""
    return Counter(packages).most_common(1)[0][0]


def _stable_foreground_package(hierarchy_package=""):
    """Prefer the hierarchy package; probe focus only when hierarchy is empty."""
    if hierarchy_package:
        return hierarchy_package

    last = ""
    for attempt in range(FOREGROUND_RETRIES):
        current = _foreground_package()
        if current:
            last = current
            return current
        if attempt + 1 < FOREGROUND_RETRIES:
            time.sleep(FOREGROUND_RETRY_DELAY)

    return last


def _node_snapshot(node):
    """Convert an XML node into the compact node shape used by Nova."""
    attrs = node.attrib
    return {
        "text": attrs.get("text", "").strip(),
        "content_description": attrs.get("content-desc", "").strip(),
        "resource_id": attrs.get("resource-id", "").strip(),
        "class": attrs.get("class", "").strip(),
        "package": attrs.get("package", "").strip(),
        "bounds": attrs.get("bounds", "").strip(),
        "clickable": attrs.get("clickable") == "true",
        "enabled": attrs.get("enabled") == "true",
        "focusable": attrs.get("focusable") == "true",
        "scrollable": attrs.get("scrollable") == "true",
        "selected": attrs.get("selected") == "true",
        "checked": attrs.get("checked") == "true",
    }


def _parse_hierarchy(xml_text, include_nodes):
    """Parse a UI hierarchy and preserve the nearest actionable ancestor."""
    root = ET.fromstring(xml_text)
    nodes = []

    parent_map = {}
    for parent in root.iter("node"):
        for child in list(parent):
            if child.tag == "node":
                parent_map[child] = parent

    for node in root.iter("node"):
        item = _node_snapshot(node)
        if not any((item["text"], item["content_description"], item["resource_id"], item["class"])):
            continue

        if include_nodes and not item["clickable"]:
            ancestor = parent_map.get(node)
            while ancestor is not None:
                ancestor_item = _node_snapshot(ancestor)
                if ancestor_item["enabled"] and ancestor_item["clickable"]:
                    item["actionable_ancestor"] = ancestor_item
                    break
                ancestor = parent_map.get(ancestor)

        nodes.append(item)

    return nodes


def observe_android(include_nodes=False):
    """Capture Android UI with bounded retries for transient dump failures."""
    try:
        command = (
            f"rm -f {DUMP_PATH} && "
            f"/system/bin/uiautomator dump --compressed {DUMP_PATH "
            f">/dev/null 2>&1 && cat {DUMP_PATH}"
        )

        result = None
        for attempt in range(OBSERVE_RETRIES):
            result = run_root(command, timeout=OBSERVE_TIMEOUT_SECONDS)
            if result.returncode == 0 and (result.stdout or "").strip():
                break
            if attempt + 1 < OBSERVE_RETRIES:
                time.sleep(OBSERVE_RETRY_DELAY)

        if result.returncode != 0:
            cached = run_root(f"cat {DUMP_PATH}", timeout=2)
            if cached.returncode == 0 and (cached.stdout or "").strip():
                try:
                    _parse_hierarchy(cached.stdout, include_nodes)
                    result = cached
                except ET.ParseError:
                    pass

        if result.returncode != 0:
            foreground_package = _foreground_package()
            return {
                "success": False,
                "verified": False,
                "nodes": [] if include_nodes else None,
                "foreground_package": foreground_package,
                "message": (result.stderr or result.stdout or "UI observation failed").strip(),
            }

        xml_text = result.stdout
        if not xml_text.strip():
            foreground_package = _foreground_package()
            return {
                "success": False,
                "verified": False,
                "nodes": [] if include_nodes else None,
                "foreground_package": foreground_package,
                "message": "Android UI observation produced no XML snapshot.",
            }

        nodes = _parse_hierarchy(xml_text, include_nodes)
        hierarchy_package = _infer_foreground_from_nodes(nodes)
        foreground_package = _stable_foreground_package(hierarchy_package)

        state = summarize_ui(nodes)
        state["foreground_package"] = foreground_package

        response = {
            "success": True,
            "verified": True,
            "node_count": len(nodes),
            "foreground_package": foreground_package,
            "state": state,
            "summary": format_ui_summary(state),
            "message": "Current Android UI snapshot captured successfully.",
        }

        if include_nodes:
            response["nodes"] = nodes

        return response

    except Exception as e:
        return {
            "success": False,
            "verified": False,
            "nodes": [] if include_nodes else None,
            "foreground_package": "",
            "message": str(e),
        }
