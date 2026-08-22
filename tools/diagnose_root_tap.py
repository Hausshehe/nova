"""Isolate rooted Android tap execution from Nova's planner and verifier."""

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

from navigation.actions import scroll
from navigation.observer import observe_screen
from navigation.resolver import resolve_target
from navigation.state import ObservationQuality, Resolution
from tools.android_root import run_root

SETTINGS = "com.android.settings"


def run(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


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
    parser.add_argument("target", nargs="?", default="App Management")
    args = parser.parse_args()

    events: list[dict] = []

    events.append({"event": "launch_settings", **run(["am", "start", "-a", "android.settings.SETTINGS"])})
    settings = wait_for_settings()
    events.append({"event": "settings_foreground", "package": settings.foreground_package, "quality": settings.observation_quality.value})
    if settings.foreground_package != SETTINGS:
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    before = observe_screen(previous=settings, include_nodes=True)
    events.append({"event": "before_scroll", "quality": before.observation_quality.value, "scrollable_regions": before.scrollable_regions, "visible_text": before.visible_text[:30]})
    if before.observation_quality is not ObservationQuality.VALID or not before.scrollable:
        events.append({"event": "failure", "stage": "before_scroll"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    scroll_result = scroll(before, "down")
    events.append({"event": "scroll", "success": scroll_result.success, "message": scroll_result.message, "bounds": scroll_result.bounds})
    if not scroll_result.success:
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    time.sleep(0.5)
    after = observe_screen(previous=before, include_nodes=True)
    match = resolve_target(after, args.target)
    events.append({"event": "resolve", "resolution": match.resolution.value, "label": match.label, "node": match.node})
    if match.resolution is not Resolution.FOUND or not match.node:
        events.append({"event": "failure", "stage": "resolve", "reason": match.reason})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    bounds = str(match.node.get("bounds", ""))
    ancestor = match.node.get("actionable_ancestor") if isinstance(match.node.get("actionable_ancestor"), dict) else None
    tap_node = ancestor or match.node
    bounds = str(tap_node.get("bounds", bounds))
    import re
    parsed = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not parsed:
        events.append({"event": "failure", "stage": "bounds", "bounds": bounds})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1
    left, top, right, bottom = map(int, parsed.groups())
    x = (left + right) // 2
    y = (top + bottom) // 2

    command = f"input tap {x} {y}"
    started = time.monotonic()
    result = run_root(command, timeout=3.0)
    events.append({
        "event": "root_tap",
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "duration_ms": round((time.monotonic() - started) * 1000, 1),
    })

    for attempt in range(1, 7):
        time.sleep(0.35)
        current = observe_screen(previous=after, include_nodes=True, retries=2, settle_seconds=0.15)
        events.append({
            "event": "verification",
            "attempt": attempt,
            "package": current.foreground_package,
            "quality": current.observation_quality.value,
            "meaningful_transition": after.semantic_signature() != current.semantic_signature(),
            "visible_text": current.visible_text[:25],
        })
        if current.observation_quality is ObservationQuality.VALID and current.semantic_signature() != after.semantic_signature():
            events.append({"event": "success", "reason": "Root tap produced a fresh, changed UI hierarchy."})
            print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
            return 0

    events.append({"event": "failure", "stage": "verification", "reason": "Root tap returned but no changed live UI hierarchy was observed."})
    print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
