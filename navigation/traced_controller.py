"""Non-invasive diagnostics wrapper for the existing navigation controller."""

from __future__ import annotations

import time
from typing import Iterable, Optional

from .controller import NavigationController, NavigationResult
from .diagnostics import DiagnosticTrace


class TracedNavigationController:
    """Wrap NavigationController and record a diagnostic execution timeline.

    The wrapped controller is unchanged. Diagnostics observe the controller's
    public result and timing only, so enabling tracing cannot alter navigation
    behavior.
    """

    def __init__(self, controller: Optional[NavigationController] = None, *, trace: Optional[DiagnosticTrace] = None) -> None:
        self.controller = controller or NavigationController()
        self.trace = trace or DiagnosticTrace(enabled=True)

    def navigate_target(
        self,
        target: str,
        *,
        installed_packages: Optional[Iterable[str]] = None,
        expected_foreground_package: Optional[str] = None,
        initial_direction: str = "down",
    ) -> NavigationResult:
        self.trace.record(
            "goal_step",
            "navigate_target",
            target=target,
            initial_direction=initial_direction,
            expected_foreground_package=expected_foreground_package or "",
        )
        started = time.monotonic()
        self.trace.decision(
            "controller_start",
            target=target,
        )

        try:
            result = self.controller.navigate_target(
                target,
                installed_packages=installed_packages,
                expected_foreground_package=expected_foreground_package,
                initial_direction=initial_direction,
            )
        except Exception as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000, 1)
            self.trace.failure(
                "controller_exception",
                target=target,
                elapsed_ms=elapsed_ms,
                error=repr(exc),
            )
            raise

        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        action_data = None
        if result.action is not None:
            action_data = {
                "success": result.action.success,
                "action": result.action.action,
                "message": result.action.message,
                "bounds": result.action.bounds,
            }
            if getattr(result.action, "duration_ms", None) is not None:
                action_data["duration_ms"] = result.action.duration_ms
            if getattr(result.action, "executor_returncode", None) is not None:
                action_data["executor_returncode"] = result.action.executor_returncode

        self.trace.record(
            "controller_result",
            result.state.value,
            target=target,
            success=result.success,
            verified=result.verified,
            elapsed_ms=elapsed_ms,
            scroll_count=result.scroll_count,
            direction=result.direction,
            message=result.message,
            history=[state.value for state in result.history],
            action=action_data,
            verification=(
                {
                    "success": result.verification.success,
                    "reason": result.verification.reason,
                    "target_resolved": result.verification.target_resolved,
                }
                if result.verification is not None
                else None
            ),
        )

        if not result.success:
            self.trace.failure(
                "navigation_failure",
                target=target,
                state=result.state.value,
                message=result.message,
                elapsed_ms=elapsed_ms,
            )
        else:
            self.trace.decision(
                "navigation_success",
                target=target,
                elapsed_ms=elapsed_ms,
            )
        return result
