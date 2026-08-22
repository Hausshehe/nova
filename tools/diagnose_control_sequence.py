"""Run a bounded live Android-control reliability sequence.

The probe deliberately bypasses the AI planner so failures can be attributed to
observation, semantic resolution, action execution, or verification.

Every post-action wait has a hard observation budget. There is no open-ended
polling loop and no repeated action inside this diagnostic.
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


def run(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def wait_for(predicate, *, previous=None, max_observations: int = 3):
    """Observe at most a fixed number of times; never poll until a wall-clock timeout."""
    budget = max(1, min(int(max_observations), 3))
    last = previous
    for _ in range(budget):
        last = observe_screen(previous=last, include_nodes=True, retries=1, settle_seconds=0.0)
        if predicate(last):
            return last
    return last


def valid(snapshot) -> bool:
    return snapshot is not None and snapshot.observation_quality is ObservationQuality.VALID


def has_text(snapshot, wanted: str) -> bool:
    wanted = wanted.strip().lower()
    return bool(snapshot) and any(str(text).strip().lower() == wanted for text in snapshot.visible_text)


def contains_text(snapshot, wanted: str) -> bool:
    wanted = wanted.strip().lower()
    return bool(snapshot) and any(wanted in str(text).strip().lower() for text in snapshot.visible_text)


def emit(events: list[dict], event: str, **payload) -> None:
    """Append one structured event; never mix diagnostic output into UI observations."""
    events.append({"event": event, **payload})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--visible-target", default="Bluetooth")
    parser.add_argument("--scroll-target", default="App Management")
    args = parser.parse_args()

    events: list[dict] = []

    emit(events, "launch_settings", **run(["am", "start", "-a", "android.settings.SETTINGS"]))
    settings = wait_for(
        lambda s: valid(s) and s.foreground_package == SETTINGS,
        max_observations=3,
    )
    emit(
        events,
        "settings_ready",
        package=getattr(settings, "foreground_package", ""),
        quality=getattr(getattr(settings, "observation_quality", None), "value", "UNKNOWN"),
        visible_text=getattr(settings, "visible_text", ())[:25],
    )
    if not valid(settings) or settings.foreground_package != SETTINGS:
        emit(events, "failure", stage="settings_ready", reason="Settings did not become a valid observed foreground state within the bounded observation budget.")
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # 1) Visible target activation.
    visible_match = resolve_target(settings, args.visible_target)
    emit(
        events,
        "visible_target_resolution",
        target=args.visible_target,
        resolution=visible_match.resolution.value,
        label=visible_match.label,
        node=visible_match.node,
    )
    if visible_match.resolution is not Resolution.FOUND or visible_match.node is None:
        emit(events, "failure", stage="visible_resolution", reason=visible_match.reason)
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    visible_action = activate_node(visible_match.node)
    emit(
        events,
        "visible_target_activation",
        success=visible_action.success,
        message=visible_action.message,
        bounds=visible_action.bounds,
        executor_returncode=visible_action.executor_returncode,
    )
    if not visible_action.success:
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    bluetooth = wait_for(
        lambda s: valid(s)
        and s.foreground_package == SETTINGS
        and contains_text(s, "Bluetooth")
        and has_text(s, "Navigate up"),
        previous=settings,
        max_observations=3,
    )
    bluetooth_changed = valid(bluetooth) and settings.semantic_signature() != bluetooth.semantic_signature()
    emit(
        events,
        "visible_target_verification",
        target=args.visible_target,
        package=getattr(bluetooth, "foreground_package", ""),
        quality=getattr(getattr(bluetooth, "observation_quality", None), "value", "UNKNOWN"),
        meaningful_transition=bluetooth_changed,
        visible_text=getattr(bluetooth, "visible_text", ())[:25],
    )
    if not valid(bluetooth) or not bluetooth_changed:
        emit(events, "failure", stage="visible_verification", reason="No changed verified Bluetooth destination was observed within the bounded budget.")
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # 2) Back and verify return to the Settings root page.
    back_result = back_android()
    emit(events, "back", **back_result)
    returned = wait_for(
        lambda s: valid(s)
        and s.foreground_package == SETTINGS
        and has_text(s, "Settings")
        and has_text(s, "Search settings"),
        previous=bluetooth,
        max_observations=3,
    )
    emit(
        events,
        "back_verification",
        package=getattr(returned, "foreground_package", ""),
        quality=getattr(getattr(returned, "observation_quality", None), "value", "UNKNOWN"),
        visible_text=getattr(returned, "visible_text", ())[:25],
    )
    if not valid(returned) or not has_text(returned, "Search settings"):
        emit(events, "failure", stage="back_verification", reason="Back did not return to the expected Settings root state within the bounded budget.")
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # 3) Scroll exactly once and resolve the target from fresh UI state.
    scroll_before = observe_screen(previous=returned, include_nodes=True, retries=1, settle_seconds=0.0)
    emit(
        events,
        "scroll_before",
        quality=getattr(getattr(scroll_before, "observation_quality", None), "value", "UNKNOWN"),
        scrollable_regions=getattr(scroll_before, "scrollable_regions", ()),
        visible_text=getattr(scroll_before, "visible_text", ())[:25],
    )
    if not valid(scroll_before) or not scroll_before.scrollable:
        emit(events, "failure", stage="scroll_precondition", reason="No valid live scrollable region.")
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    scroll_action = scroll(scroll_before, "down")
    emit(
        events,
        "scroll",
        success=scroll_action.success,
        message=scroll_action.message,
        bounds=scroll_action.bounds,
        executor_returncode=scroll_action.executor_returncode,
    )
    if not scroll_action.success:
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # One bounded re-observe window is enough to absorb an Android UI settle/glitch.
    scroll_after = wait_for(
        lambda s: valid(s) and contains_text(s, args.scroll_target),
        previous=scroll_before,
        max_observations=2,
    )
    scroll_changed = valid(scroll_after) and scroll_before.semantic_signature() != scroll_after.semantic_signature()
    target_match = resolve_target(scroll_after, args.scroll_target) if valid(scroll_after) else None
    emit(
        events,
        "scroll_verification",
        meaningful_transition=scroll_changed,
        target=args.scroll_target,
        resolution=target_match.resolution.value if target_match is not None else "INVALID_OBSERVATION",
        label=target_match.label if target_match is not None else "",
        visible_text=getattr(scroll_after, "visible_text", ())[:25],
    )
    if (
        not valid(scroll_after)
        or not scroll_changed
        or target_match is None
        or target_match.resolution is not Resolution.FOUND
        or target_match.node is None
    ):
        emit(events, "failure", stage="scroll_verification", reason="Scroll did not produce a fresh verified state containing the semantic target within the bounded re-observe budget.")
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    # 4) Activate the scrolled target and require a destination-specific state.
    activation = activate_node(target_match.node)
    emit(
        events,
        "scroll_target_activation",
        target=args.scroll_target,
        success=activation.success,
        message=activation.message,
        bounds=activation.bounds,
        executor_returncode=activation.executor_returncode,
    )
    if not activation.success:
        emit(events, "failure", stage="scroll_target_activation", reason="Accessibility activation failed; no blind coordinate/root retry is performed by this probe.")
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    app_management = wait_for(
        lambda s: valid(s)
        and s.foreground_package == SETTINGS
        and has_text(s, "Apps")
        and has_text(s, "App list"),
        previous=scroll_after,
        max_observations=3,
    )
    emit(
        events,
        "scroll_target_verification",
        target=args.scroll_target,
        package=getattr(app_management, "foreground_package", ""),
        quality=getattr(getattr(app_management, "observation_quality", None), "value", "UNKNOWN"),
        visible_text=getattr(app_management, "visible_text", ())[:35],
    )
    success = (
        valid(app_management)
        and app_management.foreground_package == SETTINGS
        and has_text(app_management, "Apps")
        and has_text(app_management, "App list")
    )
    emit(
        events,
        "SUCCESS" if success else "FAILURE",
        message="All control checkpoints passed." if success else "One or more control checkpoints failed.",
    )
    print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
