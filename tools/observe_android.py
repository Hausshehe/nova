"""Observe Android UI and return both raw and compact agent-friendly state."""

import xml.etree.ElementTree as ET

from tools.android_root import run_root
from tools.android_ui import format_ui_summary, summarize_ui

DUMP_PATH = "/data/local/tmp/nova_ui.xml"
OBSERVE_TIMEOUT_SECONDS = 10


def observe_android():
    """Capture the current Android UI and summarize actionable state."""
    try:
        command = (
            f"timeout {OBSERVE_TIMEOUT_SECONDS} "
            f"/system/bin/uiautomator dump {DUMP_PATH} >/dev/null 2>&1 "
            f"&& cat {DUMP_PATH}"
        )
        result = run_root(command, timeout=OBSERVE_TIMEOUT_SECONDS + 3)
        if result.returncode != 0:
            return {
                "success": False,
                "verified": False,
                "nodes": [],
                "message": (result.stderr or result.stdout or "UI observation failed").strip(),
            }

        xml_text = result.stdout
        if not xml_text.strip():
            return {
                "success": False,
                "verified": False,
                "nodes": [],
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
        return {
            "success": True,
            "verified": True,
            "node_count": len(nodes),
            "state": state,
            "nodes": nodes,
            "summary": format_ui_summary(state),
            "message": "Current Android UI snapshot captured successfully.",
        }

    except Exception as e:
        return {
            "success": False,
            "verified": False,
            "nodes": [],
            "message": str(e),
        }
