"""Trace one accessibility scroll down to the Android service log boundary.

This is a diagnostic-only probe. It does not change navigation behavior and does
not retry the scroll. It records the live scrollable region, the accessibility
transport result, and NovaAccessibility service logs emitted for that request.
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

from navigation.actions import scroll
from navigation.observer import observe_screen

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-launch-settings", action="store_true")
    args = parser.parse_args()

    events: list[dict] = []

    if not args.no_launch_settings:
        started = run(["am", "start", "-a", "android.settings.SETTINGS"])
        events.append({"event": "launch_settings", **started})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            snap = observe_screen(previous=None, include_nodes=True, retries=1, settle_seconds=0.0)
            if snap.foreground_package == SETTINGS:
                break
            time.sleep(0.2)

    before = observe_screen(previous=None, include_nodes=True)
    events.append({
        "event": "before",
        "package": before.foreground_package,
        "quality": before.observation_quality.value,
        "scrollable_regions": before.scrollable_regions,
        "visible_text": before.visible_text[:30],
    })

    if before.foreground_package != SETTINGS:
        events.append({"event": "failure", "reason": "Settings is not foreground"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # Clear only the local diagnostic log buffer. No navigation retry is performed.
    events.append({"event": "logcat_clear", **run(["logcat", "-c"])})

    action = scroll(before, "down")
    events.append({
        "event": "scroll_request",
        "success": action.success,
        "bounds": action.bounds,
        "executor_returncode": action.executor_returncode,
        "duration_ms": action.duration_ms,
        "message": action.message,
        "transport_output": action.transport_output,
    })

    time.sleep(0.4)
    logs = run(["logcat", "-d", "-s", "NovaAccessibility:I", "*:S"])
    events.append({"event": "service_logs", **logs})

    after = observe_screen(previous=None, include_nodes=True)
    events.append({
        "event": "after",
        "package": after.foreground_package,
        "quality": after.observation_quality.value,
        "scrollable_regions": after.scrollable_regions,
        "visible_text": after.visible_text[:30],
    })
    events.append({
        "event": "comparison",
        "semantic_signature_changed": before.semantic_signature() != after.semantic_signature(),
        "visible_text_changed": before.visible_text != after.visible_text,
    })

    print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
