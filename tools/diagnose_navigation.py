"""Run one evidence-driven accessibility navigation hop.

This probe intentionally does not call the full NavigationController. It captures
one observation -> target resolution -> semantic scroll -> fresh observation ->
target resolution cycle so a real-device failure can be localized without
changing production navigation behavior.
"""

from __future__ import annotations

import argparse
import json

from navigation.actions import scroll
from navigation.diagnostics import DiagnosticTrace
from navigation.observer import observe_screen
from navigation.resolver import resolve_target
from navigation.state import Resolution, ScreenSnapshot


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


def _snapshot_data(snapshot: ScreenSnapshot):
    return {
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
        "nodes": [_node_summary(node) for node in snapshot.visible_nodes[:30]],
    }


def _match_data(match):
    return {
        "resolution": match.resolution.value,
        "target": match.target,
        "label": match.label,
        "score": match.score,
        "reason": match.reason,
        "node": _node_summary(match.node) if match.node is not None else None,
    }


def run_one_scroll(target: str, direction: str = "down") -> DiagnosticTrace:
    trace = DiagnosticTrace()

    before = observe_screen(previous=None, include_nodes=True)
    trace.record("observation", "before_scroll", snapshot=_snapshot_data(before))

    before_match = resolve_target(before, target)
    trace.record("target_resolution", "before_scroll", match=_match_data(before_match))

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
    )

    if not action.success:
        trace.record(
            "failure",
            "scroll_transport_or_execution",
            message="The semantic scroll did not report success; no second scroll or recovery was attempted.",
        )
        return trace

    after = observe_screen(previous=None, include_nodes=True)
    trace.record("observation", "after_scroll", snapshot=_snapshot_data(after))
    trace.record(
        "observation_comparison",
        "after_scroll_vs_before",
        semantic_signature_changed=before.semantic_signature() != after.semantic_signature(),
        foreground_package_changed=before.foreground_package != after.foreground_package,
        visible_text_changed=before.visible_text != after.visible_text,
    )

    after_match = resolve_target(after, target)
    trace.record("target_resolution", "after_scroll", match=_match_data(after_match))

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
    parser = argparse.ArgumentParser(description="Trace one Accessibility scroll and fresh post-scroll resolution.")
    parser.add_argument("target", help="Semantic target to look for, e.g. Apps")
    parser.add_argument("--direction", choices=("down", "up"), default="down")
    args = parser.parse_args()

    trace = run_one_scroll(args.target, args.direction)
    print(json.dumps(trace.as_dict(), indent=2, ensure_ascii=False, sort_keys=True))

    return 0 if not any(event["stage"] == "failure" for event in trace.events) else 1


if __name__ == "__main__":
    raise SystemExit(main())
