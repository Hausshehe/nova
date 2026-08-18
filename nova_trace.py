"""Run Nova's deterministic navigation path with an execution trace."""

from __future__ import annotations

import json
import sys

from navigation.diagnostics import DiagnosticTrace
from navigation.goal_parser import parse_open_path
from navigation.traced_controller import TracedNavigationController
from navigation.path import OpenPathNavigator


def main() -> int:
    goal = " ".join(sys.argv[1:]).strip()
    if not goal:
        print("Usage: python nova_trace.py \"Open Settings and open Apps\"")
        return 2

    targets = parse_open_path(goal)
    trace = DiagnosticTrace(enabled=True)
    controller = TracedNavigationController(trace=trace)
    navigator = OpenPathNavigator(controller=controller)
    result = navigator.navigate(goal)

    print(json.dumps({
        "success": result.success,
        "verified": result.verified,
        "message": result.message,
        "targets": result.targets,
        "completed_targets": result.completed_targets,
        "failed_target": result.failed_target,
        "checkpoints": result.checkpoints,
    }, ensure_ascii=False, indent=2))
    print()
    print(trace.render())
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
