"""Observe the current Android UI without fixed coordinates or app scripts."""

import xml.etree.ElementTree as ET

from tools.android_root import run_root


DUMP_PATH = "/data/local/tmp/nova_ui.xml"
OBSERVE_TIMEOUT_SECONDS = 10


def observe_android():
    """Return a structured snapshot of the currently visible Android UI."""
    try:
        # uiautomator can occasionally hang on a transient Android UI state.
        # Bound the device-side operation so the persistent root shell cannot
        # leave the whole agent blocked forever.
        command = (
            f"timeout {OBSERVE_TIMEOUT_SECONDS} "
            f"/system/bin/uiautomator dump {DUMP_PATH} >/dev/null 2>&1 "
            f"&& cat {DUMP_PATH}"
        )
        result = run_root(command)
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

        return {
            "success": True,
            "verified": True,
            "node_count": len(nodes),
            "nodes": nodes,
            "message": "Current Android UI snapshot captured successfully.",
        }

    except Exception as e:
        return {
            "success": False,
            "verified": False,
            "nodes": [],
            "message": str(e),
        }
