"""Run a small live Android-control reliability sequence.

Sequence:
1. Launch Settings.
2. Tap a currently visible target (Bluetooth).
3. Verify the Bluetooth Settings destination.
4. Press Back and verify return to Settings.
5. Scroll once and semantically resolve App Management.
6. Activate App Management.
7. Verify the App Management destination.

This intentionally bypasses the AI planner so failures are attributable to
observation, semantic resolution, action execution, or verification.
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
from tools.back_android import back_android

SETTINGS = "com.android.settings"
BLUETOOTH_SETTINGS = "com.android.settings.bluetooth.BluetoothDashboardActivity"


def run(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    return {"command": command, "returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


def wait_for(predicate, timeout: float = 5.0, interval: float = 0.25):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = observe_screen(previous=last, include_nodes=True, retries=1, settle_seconds=0.0)
        if predicate(last):
            return last
        time.sleep(interval)
    return last or observe_screen(previous=None, include_nodes=True, retries=1, settle_seconds=0.0)


def valid(snapshot) -> bool:
    return snapshot is not None and snapshot.observation_quality is ObservationQuality.VALID


def has_text(snapshot, wanted: str) -> bool:
    wanted = wanted.strip().lower()
    return any(str(text).strip().lower() == wanted for text in snapshot.visible_text)


def contains_text(snapshot, wanted: str) -> bool:
    wanted = wanted.strip().lower()
    return any(wanted in str(text).strip().lower() for text in snapshot.visible_text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--visible-target", default="Bluetooth")
    parser.add_argument("--scroll-target", default="App Management")
    args = parser.parse_args()

    events: list[dict] = []

    events.append({"event": "launch_settings", **run(["am", "start", "-a", "android.settings.SETTINGS"])})
    settings = wait_for(lambda s: valid(s) and s.foreground_package == SETTINGS)
    events.append({
        "event": "settings_ready",
        "package": settings.foreground_package,
        "quality": settings.observation_quality.value,
        "visible_text": settings.visible_text[:25],
    })
    if not valid(settings) or settings.foreground_package != SETTINGS:
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # 1) Visible target activation.
    visible_match = resolve_target(settings, args.visible_target)
    events.append({
        "event": "visible_target_resolution",
        "target": args.visible_target,
        "resolution": visible_match.resolution.value,
        "label": visible_match.label,
        "node": visible_match.node,
    })
    if visible_match.resolution is not Resolution.FOUND or visible_match.node is None:
        events.append({"event": "failure", "stage": "visible_resolution", "reason": visible_match.reason})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    visible_action = activate_node(visible_match.node)
    events.append({
        "event": "visible_target_activation",
        "success": visible_action.success,
        "message": visible_action.message,
        "bounds": visible_action.bounds,
        "executor_returncode": visible_action.executor_returncode,
    })
    if not visible_action.success:
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    bluetooth = wait_for(
        lambda s: valid(s) and (
            contains_text(s, "Bluetooth")
            and s.foreground_package == SETTINGS
        )
    )
    bluetooth_changed = settings.semantic_signature() != bluetooth.semantic_signature()
    events.append({
        "event": "visible_target_verification",
        "target": args.visible_target,
        "package": bluetooth.foreground_package,
        "quality": bluetooth.observation_quality.value,
        "meaningful_transition": bluetooth_changed,
        "visible_text": bluetooth.visible_text[:25],
    })
    if not valid(bluetooth) or not bluetooth_changed:
        events.append({"event": "failure", "stage": "visible_verification", "reason": "No changed verified destination after visible target activation."})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # 2) Back and verify return to the Settings root page.
    back_result = back_android()
    events.append({"event": "back", **back_result})
    returned = wait_for(
        lambda s: valid(s)
        and s.foreground_package == SETTINGS
        and has_text(s, "Settings")
        and has_text(s, "Search settings")
    )
    events.append({
        "event": "back_verification",
        "package": returned.foreground_package,
        "quality": returned.observation_quality.value,
        "visible_text": returned.visible_text[:25],
    })
    if not valid(returned) or not has_text(returned, "Search settings"):
        events.append({"event": "failure", "stage": "back_verification", "reason": "Back did not return to the expected Settings root state."})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # 3) Scroll once and resolve the target semantically.
    scroll_before = observe_screen(previous=returned, include_nodes=True)
    events.append({
        "event": "scroll_before",
        "quality": scroll_before.observation_quality.value,
        "scrollable_regions": scroll_before.scrollable_regions,
        "visible_text": scroll_before.visible_text[:25],
    })
    if not valid(scroll_before) or not scroll_before.scrollable:
        events.append({"event": "failure", "stage": "scroll_precondition", "reason": "No valid live scrollable region."})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    scroll_action = scroll(scroll_before, "down")
    events.append({
        "event": "scroll",
        "success": scroll_action.success,
        "message": scroll_action.message,
        "bounds": scroll_action.bounds,
        "executor_returncode": scroll_action.executor_returncode,
    })
    if not scroll_action.success:
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    scroll_after = wait_for(lambda s: valid(s) and contains_text(s, args.scroll_target))
    scroll_changed = scroll_before.semantic_signature() != scroll_after.semantic_signature()
    target_match = resolve_target(scroll_after, args.scroll_target)
    events.append({
        "event": "scroll_verification",
        "meaningful_transition": scroll_changed,
        "target": args.scroll_target,
        "resolution": target_match.resolution.value,
        "label": target_match.label,
        "visible_text": scroll_after.visible_text[:25],
    })
    if not valid(scroll_after) or not scroll_changed or target_match.resolution is not Resolution.FOUND or target_match.node is None:
        events.append({"event": "failure", "stage": "scroll_verification", "reason": "Scroll did not produce a verified state containing the semantic target."})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # 4) Activate the scrolled target and require a destination-specific state.
    destination_match = target_match
    activation = activate_node(destination_match.node)
    events.append({
        "event": "scroll_target_activation",
        "target": args.scroll_target,
        "success": activation.success,
        "message": activation.message,
        "bounds": activation.bounds,
        "executor_returncode": activation.executor_returncode,
    })
    if not activation.success:
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    app_management = wait_for(
        lambda s: valid(s)
        and s.foreground_package == SETTINGS
        and has_text(s, "Apps")
        and has_text(s, "App list")
    )
    events.append({
        "event": "scroll_target_verification",
        "target": args.scroll_target,
        "package": app_management.foreground_package,
        "quality": app_management.observation_quality.value,
        "visible_text": app_management.visible_text[:35],
    })
    success = valid(app_management) and app_management.foreground_package == SETTINGS and has_text(app_management, "Apps") and has_text(app_management, "App list")
    events.append({"event": "SUCCESS" if success else "FAILURE", "message": "All control checkpoints passed." if success else "One or more control checkpoints failed."})
    print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
