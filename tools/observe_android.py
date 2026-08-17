"""Observe Android UI and return compact state for Nova's reasoning.

The full node list can still be requested by internal UI tools, but the
normal LLM-facing result intentionally omits it to prevent huge provider
requests.
"""

import re
import xml.etree.ElementTree as ET

from tools.android_root import run_root
from tools.android_ui import format_ui_summary, summarize_ui

DUMP_PATH = "/data/local/tmp/nova_ui.xml"
OBSERVE_TIMEOUT_SECONDS = 8


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


def observe_android(include_nodes=False):
    """Capture Android UI without allowing observation to block the agent.

    By default only a compact semantic summary is returned to the caller.
    ``include_nodes=True`` is reserved for internal tools such as click_node
    that actually need the raw hierarchy for selector matching.
    """
    try:
        foreground_package = _foreground_package()

        # Do not wrap uiautomator in the Android `timeout` utility.  The root
        # runner now owns the hard timeout and kills the entire process group,
        # including a stuck uiautomator child.
        command = (
            f"/system/bin/uiautomator dump --compressed {DUMP_PATH} "
            f">/dev/null 2>&1 && cat {DUMP_PATH}"
        )
        result = run_root(
            command,
            timeout=OBSERVE_TIMEOUT_SECONDS,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "verified": False,
                "nodes": [] if include_nodes else None,
                "foreground_package": foreground_package,
                "message": (
                    result.stderr
                    or result.stdout
                    or "UI observation failed"
                ).strip(),
            }

        xml_text = result.stdout
        if not xml_text.strip():
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
