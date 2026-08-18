"""Resumable multi-step navigation orchestration for Nova."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from tools.find_android_app import find_android_app
from tools.launch_android_app import launch_android_app

from .checkpoints import Checkpoint, CheckpointStore
from .controller import NavigationController, NavigationResult
from .goal_parser import parse_open_path
from .observer import observe_screen
from .state import ObservationQuality
from .verifier import verify_transition


@dataclass(frozen=True)
class PathResult:
    success: bool
    verified: bool
    targets: List[str]
    completed_targets: List[str]
    failed_target: str = ""
    checkpoints: int = 0
    message: str = ""


class OpenPathNavigator:
    """Execute a parsed open path while preserving verified checkpoints."""

    def __init__(self, controller: Optional[NavigationController] = None):
        self.controller = controller or NavigationController()
        self.checkpoints = CheckpointStore()

    def _launch_installed_app(self, target: str, packages: list[str]) -> NavigationResult:
        if len(packages) != 1:
            return NavigationResult(
                False,
                False,
                target,
                self.controller.navigate_target(target).state,
                message="Installed-app identity is ambiguous; refusing to guess a package.",
            )

        package = packages[0]
        launch = launch_android_app(package)
        if not launch.get("success"):
            return NavigationResult(
                False,
                False,
                target,
                self.controller.navigate_target(target).state,
                message=launch.get("message", "Application launch failed."),
            )

        before = observe_screen(include_nodes=True, retries=1)
        verification = verify_transition(
            before,
            expected_foreground_package=package,
            timeout_seconds=4.0,
        )
        return NavigationResult(
            verification.success,
            verification.success,
            target,
            self.controller.navigate_target(target).state,
            snapshot=verification.snapshot,
            verification=verification,
            message=(
                "Installed application launched and verified in the foreground."
                if verification.success
                else verification.reason
            ),
        )

    def navigate(self, goal: str) -> PathResult:
        targets = parse_open_path(goal)
        if not targets:
            return PathResult(False, False, [], [], message="No open-navigation targets were found.")

        completed: List[str] = []

        for index, target in enumerate(targets):
            result = self.controller.navigate_target(target)

            if not result.success:
                # A target not represented by the current screen may be a real
                # installed application. Discovery is a fallback, never the
                # primary interpretation of a visible Settings destination.
                discovery = find_android_app(target)
                packages = discovery.get("packages") or [] if isinstance(discovery, dict) else []
                if packages:
                    result = self._launch_installed_app(target, packages)

            if not result.success or not result.verified:
                return PathResult(
                    False,
                    False,
                    targets,
                    completed,
                    failed_target=target,
                    checkpoints=len(self.checkpoints.items),
                    message=result.message or f"Could not reach '{target}'.",
                )

            snapshot = result.snapshot
            if snapshot is None or snapshot.observation_quality is not ObservationQuality.VALID:
                return PathResult(
                    False,
                    False,
                    targets,
                    completed,
                    failed_target=target,
                    checkpoints=len(self.checkpoints.items),
                    message=f"'{target}' was activated but no valid checkpoint snapshot was available.",
                )

            self.checkpoints.save(
                Checkpoint(
                    index=index,
                    target=target,
                    snapshot=snapshot,
                    foreground_package=snapshot.foreground_package,
                )
            )
            completed.append(target)

        return PathResult(
            True,
            True,
            targets,
            completed,
            checkpoints=len(self.checkpoints.items),
            message="All targets were reached and verified with checkpoints.",
        )
