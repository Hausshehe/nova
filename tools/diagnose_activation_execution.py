"""Trace one semantic activation after the one-scroll diagnostic boundary.

This probe deliberately does not run the full navigation controller. It launches
Settings, performs exactly one Accessibility Service scroll, resolves the semantic
Apps target against the fresh post-scroll hierarchy, activates it once through the
Accessibility Service, and records the resulting UI transition.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from navigation.actions import activate_node, scroll
from navigation.observer import observe_screen
from navigation.resolver import resolve_target
from navigation.state import ObservationQuality, Resolution

SETTINGS = "com.android.settings"


def run(command: list[str]) -> dict:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {"command": command, "error": repr(exc)}


def wait_for_settings(timeout_seconds: float = 5.0):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        snapshot = observe_screen(previous=None, include_nodes=True, retries=1, settle_seconds=0.0)
        if snapshot.foreground_package == SETTINGS:
            return snapshot
        time.sleep(0.2)
    return observe_screen(previous=None, include_nodes=True, retries=1, settle_seconds=0.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", nargs="?", default="Apps")
    parser.add_argument("--no-launch-settings", action="store_true")
    args = parser.parse_args()

    events: list[dict] = []

    if not args.no_launch_settings:
        started = run(["am", "start", "-a", "android.settings.SETTINGS"])
        events.append({"event": "launch_settings", **started})
        settings = wait_for_settings()
    else:
        settings = observe_screen(previous=None, include_nodes=True)

    events.append({
        "event": "settings_foreground",
        "package": settings.foreground_package,
        "quality": settings.observation_quality.value,
        "visible_text": settings.visible_text[:30],
    })
    if settings.foreground_package != SETTINGS:
        events.append({"event": "failure", "stage": "setup", "reason": "Settings is not foreground"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    before = observe_screen(previous=settings, include_nodes=True)
    events.append({
        "event": "before_scroll",
        "quality": before.observation_quality.value,
        "scrollable_regions": before.scrollable_regions,
        "visible_text": before.visible_text[:30],
    })
    if before.observation_quality is not ObservationQuality.VALID:
        events.append({"event": "failure", "stage": "observation", "reason": "Before-scroll hierarchy is not valid"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    before_match = resolve_target(before, args.target)
    events.append({
        "event": "before_resolution",
        "resolution": before_match.resolution.value,
        "label": before_match.label,
        "score": before_match.score,
        "reason": before_match.reason,
    })

    if before_match.resolution is Resolution.AMBIGUOUS:
        events.append({"event": "failure", "stage": "before_resolution", "reason": before_match.reason})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    if not before.scrollable:
        events.append({"event": "failure", "stage": "scroll", "reason": "No live scrollable region is available"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    action = scroll(before, "down")
    events.append({
        "event": "scroll",
        "success": action.success,
        "bounds": action.bounds,
        "executor_returncode": action.executor_returncode,
        "message": action.message,
        "transport_output": action.transport_output,
    })
    if not action.success:
        events.append({"event": "failure", "stage": "scroll", "reason": action.message})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    time.sleep(0.45)
    after = observe_screen(previous=before, include_nodes=True)
    events.append({
        "event": "after_scroll",
        "quality": after.observation_quality.value,
        "scrollable_regions": after.scrollable_regions,
        "visible_text": after.visible_text[:30],
        "semantic_signature_changed": before.semantic_signature() != after.semantic_signature(),
        "visible_text_changed": before.visible_text != after.visible_text,
    })

    match = resolve_target(after, args.target)
    events.append({
        "event": "post_scroll_resolution",
        "resolution": match.resolution.value,
        "label": match.label,
        "score": match.score,
        "reason": match.reason,
        "node": match.node,
    })
    if match.resolution is not Resolution.FOUND or match.node is None:
        events.append({"event": "failure", "stage": "post_scroll_resolution", "reason": "Target was not safely resolved after the one scroll"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # This is the boundary under investigation: one live semantic activation,
    # with no retry and no root/input fallback.
    activation = activate_node(match.node)
    events.append({
        "event": "activation",
        "success": activation.success,
        "bounds": activation.bounds,
        "executor_returncode": activation.executor_returncode,
        "message": activation.message,
        "transport_output": activation.transport_output,
    })
    if not activation.success:
        events.append({"event": "failure", "stage": "activation", "reason": activation.message})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    time.sleep(0.8)
    final = observe_screen(previous=after, include_nodes=True)
    events.append({
        "event": "after_activation",
        "package": final.foreground_package,
        "quality": final.observation_quality.value,
        "visible_text": final.visible_text[:30],
        "semantic_signature_changed": after.semantic_signature() != final.semantic_signature(),
        "source_label_still_visible": args.target.lower() in {str(node.get("text") or "").strip().lower() for node in final.visible_nodes if isinstance(node, dict)},
    })

    print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
