"""Run one evidence-driven accessibility navigation hop.

This probe intentionally does not call the full NavigationController. It captures
one setup -> observation -> target resolution -> semantic scroll -> fresh
observation -> target resolution cycle so a real-device failure can be localized
without changing production navigation behavior.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from navigation.actions import scroll
from navigation.diagnostics import DiagnosticTrace
from navigation.observer import observe_screen
from navigation.resolver import resolve_target
from navigation.state import Resolution, ScreenSnapshot
from tools.accessibility_snapshot import read_accessibility_snapshot

DEFAULT_SETTINGS_PACKAGE = "com.android.settings"
DEFAULT_SETUP_TIMEOUT_SECONDS = 5.0
DEFAULT_SETUP_POLL_SECONDS = 0.20
DEFAULT_POST_SCROLL_TIMEOUT_SECONDS = 3.0
DEFAULT_POST_SCROLL_POLL_SECONDS = 0.10


def _node_summary(node):
    if not isinstance(node, dict):
        return {}
    ancestor = node.get("actionable_ancestor")
    return {"text": str(node.get("text") or "").strip(), "content_description": str(node.get("content_description") or "").strip(), "resource_id": str(node.get("resource_id") or "").strip(), "class": str(node.get("class") or ""), "package": str(node.get("package") or ""), "bounds": str(node.get("bounds") or ""), "clickable": bool(node.get("clickable")), "enabled": bool(node.get("enabled", True)), "actionable_ancestor": ({"bounds": str(ancestor.get("bounds") or ""), "clickable": bool(ancestor.get("clickable")), "enabled": bool(ancestor.get("enabled", True))} if isinstance(ancestor, dict) else None)}


def _snapshot_data(snapshot: ScreenSnapshot, *, compact: bool = False):
    data = {"foreground_package": snapshot.foreground_package, "observation_quality": snapshot.observation_quality.value, "message": snapshot.message, "node_count": len(snapshot.visible_nodes), "actionable_count": len(snapshot.actionable_nodes), "scrollable_regions": [str(region.get("bounds") or "") for region in snapshot.scrollable_regions if isinstance(region, dict)], "visible_text": list(snapshot.visible_text[:30])}
    if not compact:
        data["nodes"] = [_node_summary(node) for node in snapshot.visible_nodes[:30]]
    return data


def _match_data(match, *, compact: bool = False):
    data = {"resolution": match.resolution.value, "target": match.target, "label": match.label, "score": match.score, "reason": match.reason}
    if not compact:
        data["node"] = _node_summary(match.node) if match.node is not None else None
    return data


def _record(trace, stage, event, **data):
    """Record an event while keeping the probe usable with tiny test doubles."""
    recorder = getattr(trace, "record", None)
    if recorder is not None:
        recorder(stage, event, **data)
        return
    events = getattr(trace, "events", None)
    if events is not None and hasattr(events, "append"):
        events.append({"stage": stage, "event": event, **data})


def _launch_settings(trace, *, timeout_seconds: float = DEFAULT_SETUP_TIMEOUT_SECONDS) -> bool:
    """Launch Settings as deterministic probe setup, then wait for its live package."""
    started = time.monotonic()
    command = ["am", "start", "-a", "android.settings.SETTINGS"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5.0, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        _record(trace, "setup", "launch_settings_failed", requested=True, command=command, success=False, error=repr(exc), elapsed_ms=round((time.monotonic() - started) * 1000, 1))
        return False
    _record(trace, "setup", "launch_settings", requested=True, command=command, success=result.returncode == 0, executor_returncode=result.returncode, transport_output="\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()), elapsed_ms=round((time.monotonic() - started) * 1000, 1))
    if result.returncode != 0:
        return False
    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    while time.monotonic() < deadline:
        snapshot = observe_screen(previous=None, include_nodes=True, retries=1, settle_seconds=0.0)
        if snapshot.foreground_package == DEFAULT_SETTINGS_PACKAGE:
            _record(trace, "setup", "settings_foreground_confirmed", package=snapshot.foreground_package, observation_quality=snapshot.observation_quality.value, node_count=len(snapshot.visible_nodes), elapsed_ms=round((time.monotonic() - started) * 1000, 1))
            return True
        time.sleep(DEFAULT_SETUP_POLL_SECONDS)
    snapshot = observe_screen(previous=None, include_nodes=True, retries=1, settle_seconds=0.0)
    _record(trace, "setup", "settings_foreground_timeout", expected_package=DEFAULT_SETTINGS_PACKAGE, actual_package=snapshot.foreground_package, observation_quality=snapshot.observation_quality.value, elapsed_ms=round((time.monotonic() - started) * 1000, 1))
    return False


def _snapshot_timestamp_ms():
    data = read_accessibility_snapshot(max_age_seconds=30.0)
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get("timestamp_ms") or 0)
    except (TypeError, ValueError):
        return 0


def _wait_for_new_snapshot(before_timestamp_ms: int, *, timeout_seconds: float = DEFAULT_POST_SCROLL_TIMEOUT_SECONDS) -> int:
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    latest = before_timestamp_ms
    while time.monotonic() < deadline:
        latest = _snapshot_timestamp_ms()
        if latest > before_timestamp_ms:
            return latest
        time.sleep(DEFAULT_POST_SCROLL_POLL_SECONDS)
    return latest


def run_probe(target: str, direction: str, *, compact: bool = False, expected_package: str = DEFAULT_SETTINGS_PACKAGE):
    trace = DiagnosticTrace()
    if not _launch_settings(trace):
        return trace
    before = observe_screen(previous=None, include_nodes=True, retries=2, settle_seconds=0.0)
    _record(trace, "observation", "before_scroll", snapshot=_snapshot_data(before, compact=compact))
    before_match = resolve_target(before, target)
    _record(trace, "target_resolution", "before_scroll", match=_match_data(before_match, compact=compact))
    if before.foreground_package != expected_package:
        _record(trace, "failure", "unexpected_foreground_package", expected_package=expected_package, actual_package=before.foreground_package)
        return trace
    if before_match.resolution in {Resolution.EXACT, Resolution.FUZZY}:
        _record(trace, "decision", "target_already_resolved", match=_match_data(before_match, compact=compact))
        return trace
    if not before.scrollable_regions:
        _record(trace, "failure", "no_scrollable_region")
        return trace
    _record(trace, "decision", "scroll", direction=direction, scrollable_regions=[str(region.get("bounds") or "") for region in before.scrollable_regions])
    before_timestamp = _snapshot_timestamp_ms()
    action_result = scroll(before, direction)
    _record(trace, "scroll_request", "accessibility_scroll", requested=True, direction=direction, success=bool(action_result.success), executor_returncode=action_result.returncode, message=action_result.message, transport_output=action_result.raw_output, elapsed_ms=round((time.monotonic() - trace.started_at) * 1000, 1) if hasattr(trace, "started_at") else 0.0)
    if not action_result.success:
        _record(trace, "failure", "scroll_transport_or_execution", message="The semantic scroll did not report success; no second scroll or recovery was attempted.")
        return trace
    after_timestamp = _wait_for_new_snapshot(before_timestamp)
    if after_timestamp <= before_timestamp:
        _record(trace, "failure", "post_scroll_observation_timeout", before_timestamp_ms=before_timestamp, latest_timestamp_ms=after_timestamp, message="Accessibility scroll was accepted, but no newer published accessibility snapshot arrived within the bounded diagnostic window.")
        return trace
    after = observe_screen(previous=None, include_nodes=True, retries=1, settle_seconds=0.0)
    _record(trace, "observation", "after_scroll", snapshot=_snapshot_data(after, compact=compact), snapshot_timestamp_ms=after_timestamp)
    _record(trace, "observation_comparison", "after_scroll_vs_before", foreground_package_changed=after.foreground_package != before.foreground_package, semantic_signature_changed=after.semantic_signature != before.semantic_signature, visible_text_changed=after.visible_text != before.visible_text)
    after_match = resolve_target(after, target)
    _record(trace, "target_resolution", "after_scroll", match=_match_data(after_match, compact=compact))
    if after_match.resolution not in {Resolution.EXACT, Resolution.FUZZY}:
        _record(trace, "decision", "target_not_resolved_after_scroll", action="NO_ACTIVATION", reason="The fresh post-scroll hierarchy did not resolve the target.")
    else:
        _record(trace, "decision", "target_resolved_after_scroll", action="NO_ACTIVATION", match=_match_data(after_match, compact=compact))
    return trace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--direction", choices=["up", "down"], default="down")
    parser.add_argument("--expected-package", default=DEFAULT_SETTINGS_PACKAGE)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    trace = run_probe(args.target, args.direction, compact=args.compact, expected_package=args.expected_package)
    print(json.dumps({"events": trace.events}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
