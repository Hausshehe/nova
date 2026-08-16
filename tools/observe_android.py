"""Observe the current Android UI without relying on fixed coordinates or app-specific scripts."""

import subprocess
import xml.etree.ElementTree as ET


DUMP_PATH = "/data/local/tmp/nova_ui.xml"


def _run_root(command):
    process = subprocess.run(
        ["su", "-c", command],
        capture_output=True,
        text=True,
        timeout=15,
    )

    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip() or "root command failed")

    return process.stdout


def observe_android():
    """Return a structured snapshot of the currently visible Android UI."""
    try:
        _run_root(
            f"uiautomator dump {DUMP_PATH} >/dev/null 2>&1 && cat {DUMP_PATH}"
        )

        xml_text = _run_root(f"cat {DUMP_PATH}")
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
