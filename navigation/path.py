"""Resumable multi-step navigation orchestration for Nova."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from tools.find_android_app import find_android_app
from tools.launch_android_app import launch_android_app

from .checkpoints import Checkpoint, CheckpointStore
from .controller import NavigationController, NavigationResult, NavigationState
from .goal_parser import parse_open_path
from .observer import observe_screen
from .resolver import resolve_target
from .state import ObservationQuality, ScreenSnapshot, Resolution
from .verifier import verify_transition


@dataclass(frozen=True)
class PathResult:
    success: bool
    verified: bool
    targets: List[str]
    completed_targets: List[str]
    failed_target: str = ""
    checkpoints: int = 0
    resumed_from_checkpoint: bool = False
    message: str = ""


class OpenPathNavigator:
    """Execute a parsed open path while preserving verified checkpoints."""

    def __init__(
        self,
        controller: Optional[NavigationController] = None,
        *,
        initial_direction: str = "down",
    ):
        self.controller = controller or NavigationController()
        self.initial_direction = str(initial_direction or "down").strip().lower()
        if self.initial_direction not in {"up", "down"}:
            self.initial_direction = "down"
        self.checkpoints = CheckpointStore()

    def _navigate_target(self, target: str) -> NavigationResult:
        return self.controller.navigate_target(
            target,
            initial_direction=self.initial_direction,
        )

    def _launch_installed_app(self, target: str, packages: list[str]) -> NavigationResult:
        if len(packages) != 1:
            return NavigationResult(
                False,
                False,
                target,
                NavigationState.FAILURE,
                message="Installed-app identity is ambiguous; refusing to guess a package.",
            )

        package = packages[0]
        before = observe_screen(include_nodes=True, retries=1)
        if before.observation_quality is not ObservationQuality.VALID:
            return NavigationResult(
                False,
                False,
                target,
                NavigationState.RECOVER,
                snapshot=before,
                message="Could not obtain a valid pre-launch checkpoint.",
            )

        launch = launch_android_app(package)
        if not launch.get("success"):
            return NavigationResult(
                False,
                False,
                target,
                NavigationState.FAILURE,
                snapshot=before,
                message=launch.get("message", "Application launch failed."),
            )

        verification = verify_transition(
            before,
            expected_foreground_package=package,
            timeout_seconds=4.0,
        )
        return NavigationResult(
            verification.success,
            verification.success,
            target,
            NavigationState.SUCCESS if verification.success else NavigationState.FAILURE,
            snapshot=verification.snapshot,
            verification=verification,
            message=(
                "Installed application launched and verified in the foreground."
                if verification.success
                else verification.reason
            ),
        )

    def _retry_from_latest_checkpoint(self, index: int, target: str) -> Optional[NavigationResult]:
        """Retry safely from the last verified context or a valid same-app continuation."""
        if index <= 0 or self.checkpoints.latest is None:
            return None

        current = observe_screen(include_nodes=True, retries=1)
        if current.observation_quality is not ObservationQuality.VALID:
            return None

        if self.checkpoints.matches_current(current):
            return self._navigate_target(target)

        # A failed navigation may have legitimately moved deeper into the same
        # foreground app before verification failed (for example, after opening
        # an app list). If the target is safely resolvable on that fresh screen,
        # retry from there rather than restarting the entire path or launching
        # an installed package directly.
        latest = self.checkpoints.latest
        if latest is None or current.foreground_package != latest.foreground_package:
            return None

        match = resolve_target(current, target)
        if match.resolution is not Resolution.FOUND or match.node is None:
            return None

        return self._navigate_target(target)

    def navigate(self, goal: str) -> PathResult:
        targets = parse_open_path(goal)
        if not targets:
            return PathResult(False, False, [], [], message="No open-navigation targets were found.")

        completed: List[str] = []
        resumed_from_checkpoint = False

        for index, target in enumerate(targets):
            result = self._navigate_target(target)

            # Direct package launch is only a safe fallback for the first
            # destination. Later destinations must be reached through the
            # current screen so a goal such as Settings -> Apps -> YouTube
            # cannot silently skip the requested App-list interaction.
            if index == 0 and not result.success:
                discovery = find_android_app(target)
                packages = discovery.get("packages") or [] if isinstance(discovery, dict) else []
                if packages:
                    result = self._launch_installed_app(target, packages)

            if not result.success or not result.verified:
                retry = self._retry_from_latest_checkpoint(index, target)
                if retry is not None and retry.success and retry.verified:
                    result = retry
                    resumed_from_checkpoint = True

            if not result.success or not result.verified:
                return PathResult(
                    False,
                    False,
                    targets,
                    completed,
                    failed_target=target,
                    checkpoints=len(self.checkpoints.items),
                    resumed_from_checkpoint=resumed_from_checkpoint,
                    message=result.message or f"Could not reach '{target}'.",
                )

            snapshot: Optional[ScreenSnapshot] = result.snapshot
            if snapshot is None or snapshot.observation_quality is not ObservationQuality.VALID:
                return PathResult(
                    False,
                    False,
                    targets,
                    completed,
                    failed_target=target,
                    checkpoints=len(self.checkpoints.items),
                    resumed_from_checkpoint=resumed_from_checkpoint,
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
            resumed_from_checkpoint=resumed_from_checkpoint,
            message="All targets were reached and verified with checkpoints.",
        )