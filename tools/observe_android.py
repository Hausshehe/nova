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
# OEM Settings screens containing large application lists can occasionally
# need more than 8 seconds for uiautomator to produce a fresh hierarchy.
# Keep this bounded so a genuinely stuck dump still returns control to Nova.
OBSERVE_TIMEOUT_SECONDS = 12
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
    """Infer the foreground package from the UI hierarchy as a fallback.

    Some OEM Android builds can briefly return stale/empty focus information
    while the accessibility hierarchy already belongs to the new screen. In
    that case, use the most common non-empty package in the current hierarchy.
    """
    packages = [
        node.get("package", "").strip()
        for node in nodes
        if isinstance(node, dict) and node.get("package", "").strip()
    ]
    if not packages:
        return ""
    return Counter(packages).most_common(1)[0][0]


def _stable_foreground_package(hierarchy_package=""):
    """Prefer a fresh focus result and retry briefly during Activity changes."""
    last = ""
    for attempt in range(FOREGROUND_RETRIES):
        current = _foreground_package()
        if current:
            last = current
            if not hierarchy_package or current == hierarchy_package:
                return current
        if attempt + 1 < FOREGROUND_RETRIES:
            time.sleep(FOREGROUND_RETRY_DELAY)

    return hierarchy_package or last


def observe_android(include_nodes=False):
    """Capture Android UI without allowing observation to block the agent."""
    try:
        command = (
            f"/system/bin/uiautomator dump --compressed {DUMP_PATH} "
            f">/dev/null 2>&1 && cat {DUMP_PATH}"
        )
        result = run_root(command, timeout=OBSERVE_TIMEOUT_SECONDS)

        if result.returncode != 0:
            foreground_package = _foreground_package()
            return {
                "success": False,
                "verified": False,
                "nodes": [] if include_nodes else None,
                "foreground_package": foreground_package,
                "message": (
                    result.stderr or result.stdout or "UI observation failed"
                ).strip(),
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

        root = ET.fromstring(xml_text)
        nodes = []
        for node in root.iter("node"):
            attrs = node.attrib
            text = attrs.get("text", "").strip()
            description = attrs.get("content-desc", "").strip()
            resource_id = attrs.get("resource-id", "").strip()
            class_name = attrs.get("class", "").strip()
            package = attrs.get("package", "").strip()
            bounds = attrs.get("bounds", "").strip()

            if not any((text, description, resource_id, class_name)):
                continue

            nodes.append({
                "text": text,
                "content_description": description,
                "resource_id": resource_id,
                "class": class_name,
                "package": package,
                "bounds": bounds,
                "clickable": attrs.get("clickable") == "true",
                "enabled": attrs.get("enabled") == "true",
                "focusable": attrs.get("focusable") == "true",
                "scrollable": attrs.get("scrollable") == "true",
                "selected": attrs.get("selected") == "true",
                "checked": attrs.get("checked") == "true",
            })

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
