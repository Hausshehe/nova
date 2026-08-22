"""Exercise Nova's adaptive navigation controller with explicit state boundaries.

Sequence:
1. Start Settings with Android's force-stop-before-launch flag.
2. Establish a fresh Settings-root observation.
3. Let NavigationController reach Bluetooth.
4. Send Back and establish a fresh Settings-root observation.
5. Let NavigationController reach Apps.

This diagnostic separates Android launch/back stabilization from target navigation,
starts every trial from a clean Settings task, and never verifies a post-action
state using the pre-action snapshot.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from navigation.controller import NavigationController
from navigation.observer import observe_screen
from navigation.state import ObservationQuality
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


def root_settings(snapshot) -> bool:
    return (
        snapshot is not None
        and snapshot.observation_quality is ObservationQuality.VALID
        and snapshot.foreground_package == SETTINGS
        and "Settings" in snapshot.visible_text
        and "Search settings" in snapshot.visible_text
    )


def fresh_settings_root(max_observations: int = 4):
    observations = []
    for _ in range(max(1, min(max_observations, 4))):
        time.sleep(0.35)
        current = observe_screen(previous=None, include_nodes=True, retries=3, settle_seconds=0.35)
        observations.append(current)
        if root_settings(current):
            return current, len(observations)
    return observations[-1] if observations else None, len(observations)


def main() -> int:
    events: list[dict] = []

    # Termux's `am` implementation does not expose the platform `force-stop`
    # subcommand. `am start -S` is the supported equivalent: force-stop the
    # target package before launching the Settings activity.
    launch = run(["am", "start", "-S", "-a", "android.settings.SETTINGS"])
    events.append({"event": "launch_settings_clean", **launch})
    if launch["returncode"] != 0:
        events.append({"event": "FAILURE", "stage": "launch_settings_clean"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    root, root_attempts = fresh_settings_root()
    events.append({
        "event": "settings_root_after_launch",
        "success": root_settings(root),
        "attempts": root_attempts,
        "quality": root.observation_quality.value if root else None,
        "visible_text": root.visible_text[:25] if root else [],
    })
    if not root_settings(root):
        events.append({"event": "FAILURE", "stage": "settings_root_after_launch"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    controller = NavigationController(
        observation_retries=2,
        verification_timeout=3.0,
        settle_seconds=0.45,
        max_scrolls=4,
        no_progress_before_reversal=2,
        max_transient_observations=3,
        max_activation_retries=1,
    )

    bluetooth = controller.navigate_target("Bluetooth", expected_foreground_package=SETTINGS)
    events.append({
        "event": "controller_bluetooth",
        "success": bluetooth.success,
        "verified": bluetooth.verified,
        "state": bluetooth.state.value,
        "message": bluetooth.message,
        "history": [state.value for state in bluetooth.history],
        "scroll_count": bluetooth.scroll_count,
    })
    if not bluetooth.success:
        events.append({"event": "FAILURE", "stage": "controller_bluetooth"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    back = back_android()
    events.append({"event": "back", **back})

    returned, return_attempts = fresh_settings_root()
    events.append({
        "event": "back_verification",
        "success": root_settings(returned),
        "attempts": return_attempts,
        "quality": returned.observation_quality.value if returned else None,
        "visible_text": returned.visible_text[:25] if returned else [],
    })
    if not root_settings(returned):
        events.append({"event": "FAILURE", "stage": "back_verification"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    apps = controller.navigate_target("Apps", expected_foreground_package=SETTINGS)
    events.append({
        "event": "controller_apps",
        "success": apps.success,
        "verified": apps.verified,
        "state": apps.state.value,
        "message": apps.message,
        "scroll_count": apps.scroll_count,
        "history": [state.value for state in apps.history],
        "visible_text": apps.snapshot.visible_text[:30] if apps.snapshot else [],
    })

    success = apps.success
    events.append({
        "event": "SUCCESS" if success else "FAILURE",
        "message": "Adaptive controller completed Bluetooth -> Back -> Apps." if success else "Adaptive controller did not complete the bounded sequence.",
    })
    print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
