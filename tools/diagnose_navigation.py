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
    return {
        "text": str(node.get("text") or "").strip(),
        "content_description": str(node.get("content_description") or "").strip(),
        "resource_id": str(node.get("resource_id") or "").strip(),
        "class": str(node.get("class") or ""),
        "package": str(node.get("package") or ""),
        "bounds": str(node.get("bounds") or ""),
        "clickable": bool(node.get("clickable")),
        "enabled": bool(node.get("enabled", True)),
        "actionable_ancestor": (
            {
                "bounds": str(ancestor.get("bounds") or ""),
                "clickable": bool(ancestor.get("clickable")),
                "enabled": bool(ancestor.get("enabled", True)),
            }
            if isinstance(ancestor, dict)
            else None
        ),
    }


def _snapshot_data(snapshot: ScreenSnapshot, *, compact: bool = False):
    data = {
        "foreground_package": snapshot.foreground_package,
        "observation_quality": snapshot.observation_quality.value,
        "message": snapshot.message,
        "node_count": len(snapshot.visible_nodes),
        "actionable_count": len(snapshot.actionable_nodes),
        "scrollable_regions": [
            str(region.get("bounds") or "")
            for region in snapshot.scrollable_regions
            if isinstance(region, dict)
        ],
        "visible_text": list(snapshot.visible_text[:30]),
    }
    if not compact:
        data["nodes"] = [_node_summary(node) for node in snapshot.visible_nodes[:30]]
    return data


def _match_data(match, *, compact: bool = False):
    data = {
        "resolution": match.resolution.value,
        "target": match.target,
        "label": match.label,
        "score": match.score,
        "reason": match.reason,
    }
    if not compact:
        data["node"] = _node_summary(match.node) if match.node is not None else None
    return data


def _launch_settings(trace: DiagnosticTrace, *, timeout_seconds: float = DEFAULT_SETUP_TIMEOUT_SECONDS) -> bool:
    """Launch Settings as deterministic probe setup, then wait for its live package."""
    started = time.monotonic()
    command = ["am", "start", "-a", "android.settings.SETTINGS"]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        trace.record(
            "setup",
            "launch_settings_failed",
            requested=True,
            command=command,
            success=False,
            error=repr(exc),
            elapsed_ms=round((time.monotonic() - started) * 1000, 1),
        )
        return False

    trace.record(
        "setup",
        "launch_settings",
        requested=True,
        command=command,
        success=result.returncode == 0,
        executor_returncode=result.returncode,
        transport_output="\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        ),
        elapsed_ms=round((time.monotonic() - started) * 1000, 1),
    )
    if result.returncode != 0:
        return False

    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    while time.monotonic() < deadline:
        snapshot = observe_screen(previous=None, include_nodes=True, retries=1, settle_seconds=0.0)
        if snapshot.foreground_package == DEFAULT_SETTINGS_PACKAGE:
            trace.record(
                "setup",
                "settings_foreground_confirmed",
                package=snapshot.foreground_package,
                observation_quality=snapshot.observation_quality.value,
                node_count=len(snapshot.visible_nodes),
                elapsed_ms=round((time.monotonic() - started) * 1000, 1),
            )
            return True
        time.sleep(DEFAULT_SETUP_POLL_SECONDS)

    snapshot = observe_screen(previous=None, include_nodes=True, retries=1, settle_seconds=0.0)
    trace.record(
        "setup",
        "settings_foreground_timeout",
        expected_package=DEFAULT_SETTINGS_PACKAGE,
        actual_package=snapshot.foreground_package,
        observation_quality=snapshot.observation_quality.value,
        elapsed_ms=round((time.monotonic() - started) * 1000, 1),
    )
    return False


def _snapshot_timestamp_ms():
    """Read the publisher timestamp without treating age alone as freshness."""
    data = read_accessibility_snapshot(max_age_seconds=30.0)
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get("timestamp_ms") or 0)
    except (TypeError, ValueError):
        return 0


def _wait_for_new_snapshot(before_timestamp_ms: int, *, timeout_seconds: float = DEFAULT_POST_SCROLL_TIMEOUT_SECONDS) -> int:
    """Wait for a snapshot published after the scroll request.

    A snapshot that is merely younger than the configured max age can still be
    the exact pre-action hierarchy. The diagnostic must distinguish 'recent'
    from 'newer than the action boundary'.
    """
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    latest = before_timestamp_ms
    while time.monotonic() < deadline:
        latest = _snapshot_timestamp_ms()
        if latest > before_timestamp_ms:
            return latest
        time.sleep(DEFAULT_POST_SCROLL_POLL_SECONDS)
    return latest


def run_one_scroll(
    target: str,
    direction: str = "down",
    *,
    expected_package: str | None = None,
    compact: bool = False,
) -> DiagnosticTrace:
    trace = DiagnosticTrace()

    before = observe_screen(previous=None, include_nodes=True)
    trace.record("observation", "before_scroll", snapshot=_snapshot_data(before, compact=compact))

    if expected_package and before.foreground_package != expected_package:
        trace.record(
            "failure",
            "unexpected_foreground_package",
            expected_package=expected_package,
            actual_package=before.foreground_package,
            message="Probe refused to act because the live screen is not the expected application.",
        )
        return trace

    before_match = resolve_target(before, target)
    trace.record("target_resolution", "before_scroll", match=_match_data(before_match, compact=compact))

    if not before.valid:
        trace.record(
            "failure",
            "invalid_before_observation",
            message="The pre-scroll hierarchy was not valid, so no action was attempted.",
        )
        return trace

    if before_match.resolution in {Resolution.INVALID_OBSERVATION, Resolution.AMBIGUOUS}:
        trace.record(
            "failure",
            "unsafe_before_resolution",
            message="The target resolution was not safe enough to justify a scroll.",
            resolution=before_match.resolution.value,
        )
        return trace

    if before_match.node is not None:
        trace.record(
            "decision",
            "target_already_visible",
            action="ACTIVATE_NOT_PERFORMED_BY_PROBE",
            reason="The target is already present; this probe intentionally stops before activation.",
        )
        return trace

    if not before.scrollable:
        trace.record(
            "failure",
            "no_scrollable_region",
            message="The target is not visible and the pre-scroll observation exposes no scrollable region.",
        )
        return trace

    trace.record(
        "decision",
        "scroll",
        direction=direction,
        scrollable_regions=[
            str(region.get("bounds") or "")
            for region in before.scrollable_regions
            if isinstance(region, dict)
        ],
    )

    before_timestamp_ms = _snapshot_timestamp_ms()
    action = scroll(before, direction)
    trace.record(
        "scroll_request",
        "accessibility_scroll",
        requested=True,
        direction=direction,
        success=action.success,
        bounds=action.bounds,
        duration_ms=action.duration_ms,
        executor_returncode=action.executor_returncode,
        message=action.message,
        transport_output=action.transport_output,
        before_snapshot_timestamp_ms=before_timestamp_ms,
    )

    if not action.success:
        trace.record(
            "failure",
            "scroll_transport_or_execution",
            message="The semantic scroll did not report success; no second scroll or recovery was attempted.",
        )
        return trace

    after_timestamp_ms = _wait_for_new_snapshot(before_timestamp_ms)
    if after_timestamp_ms <= before_timestamp_ms:
        trace.record(
            "failure",
            "post_scroll_observation_timeout",
            message="Accessibility accepted the scroll, but no newer published hierarchy arrived within the bounded diagnostic window.",
            before_snapshot_timestamp_ms=before_timestamp_ms,
            latest_snapshot_timestamp_ms=after_timestamp_ms,
            timeout_seconds=DEFAULT_POST_SCROLL_TIMEOUT_SECONDS,
        )
        return trace

    after = observe_screen(previous=None, include_nodes=True)
    trace.record(
        "observation", "after_scroll", snapshot=_snapshot_data(after, compact=compact),
        snapshot_timestamp_ms=after_timestamp_ms,
    )
    trace.record(
        "observation_comparison",
        "after_scroll_vs_before",
        semantic_signature_changed=before.semantic_signature() != after.semantic_signature(),
        foreground_package_changed=before.foreground_package != after.foreground_package,
        visible_text_changed=before.visible_text != after.visible_text,
    )

    after_match = resolve_target(after, target)
    trace.record("target_resolution", "after_scroll", match=_match_data(after_match, compact=compact))

    if after_match.resolution is Resolution.AMBIGUOUS:
        trace.record(
            "failure",
            "ambiguous_after_resolution",
            message="The fresh post-scroll hierarchy contains competing target candidates; activation is unsafe.",
        )
        return trace

    if after_match.node is not None:
        trace.record(
            "decision",
            "activation_ready",
            action="ACTIVATE_NOT_PERFORMED_BY_PROBE",
            reason="A fresh post-scroll resolution found the target. Activation is deliberately isolated from this experiment.",
        )
    else:
        trace.record(
            "decision",
            "target_not_resolved_after_scroll",
            action="NO_ACTIVATION",
            reason="The fresh post-scroll hierarchy did not resolve the target.",
        )

    return trace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trace one Accessibility scroll and fresh post-scroll resolution."
    )
    parser.add_argument("target", help="Semantic target to look for, e.g. Apps")
    parser.add_argument("--direction", choices=("down", "up"), default="down")
    parser.add_argument(
        "--expected-package",
        default=DEFAULT_SETTINGS_PACKAGE,
        help="Refuse to act unless the live foreground package matches this value.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Omit per-node dumps so real-device traces stay readable.",
    )
    parser.add_argument(
        "--no-launch-settings",
        action="store_true",
        help="Do not launch Settings before probing.",
    )
    args = parser.parse_args()

    trace = DiagnosticTrace()
    if not args.no_launch_settings and not _launch_settings(trace):
        print(json.dumps(trace.as_dict(), indent=2, ensure_ascii=False, sort_keys=True))
        return 1

    probe_trace = run_one_scroll(
        args.target,
        args.direction,
        expected_package=args.expected_package,
        compact=args.compact,
    )
    trace.events.extend(probe_trace.events)
    print(json.dumps(trace.as_dict(), indent=2, ensure_ascii=False, sort_keys=True))

    return 0 if not any(event["stage"] == "failure" for event in trace.events) else 1


if __name__ == "__main__":
    raise SystemExit(main())
