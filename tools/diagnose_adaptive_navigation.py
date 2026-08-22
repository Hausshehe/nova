"""Exercise Nova's actual adaptive navigation controller on a live Android device.

Sequence:
1. Launch Settings.
2. Let NavigationController reach Bluetooth.
3. Send Back and boundedly verify the Settings root.
4. Let NavigationController reach App Management via the semantic goal "Apps".

This is intentionally different from diagnose_control_sequence.py: it exercises
NavigationController's bounded recovery rather than calling low-level actions
without the controller.
"""

from __future__ import annotations

import json
import subprocess
import sys
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


def bounded_back_verification(previous, max_observations: int = 3):
    current = previous
    for _ in range(max(1, min(max_observations, 3))):
        current = observe_screen(previous=current, include_nodes=True, retries=1, settle_seconds=0.0)
        if root_settings(current):
            return current
    return current


def main() -> int:
    events: list[dict] = []
    events.append({"event": "launch_settings", **run(["am", "start", "-a", "android.settings.SETTINGS"])})

    controller = NavigationController(
        observation_retries=2,
        verification_timeout=3.0,
        settle_seconds=0.35,
        max_scrolls=4,
        no_progress_before_reversal=2,
        max_transient_observations=3,
        max_activation_retries=1,
    )

    bluetooth = controller.navigate_target(
        "Bluetooth",
        expected_foreground_package=SETTINGS,
    )
    events.append({
        "event": "controller_bluetooth",
        "success": bluetooth.success,
        "verified": bluetooth.verified,
        "state": bluetooth.state.value,
        "message": bluetooth.message,
        "history": [state.value for state in bluetooth.history],
    })
    if not bluetooth.success:
        events.append({"event": "FAILURE", "stage": "controller_bluetooth"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    back = back_android()
    events.append({"event": "back", **back})
    returned = bounded_back_verification(bluetooth.snapshot)
    events.append({
        "event": "back_verification",
        "success": root_settings(returned),
        "quality": returned.observation_quality.value,
        "visible_text": returned.visible_text[:20],
    })
    if not root_settings(returned):
        events.append({"event": "FAILURE", "stage": "back_verification"})
        print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
        return 1

    apps = controller.navigate_target(
        "Apps",
        expected_foreground_package=SETTINGS,
    )
    events.append({
        "event": "controller_apps",
        "success": apps.success,
        "verified": apps.verified,
        "state": apps.state.value,
        "message": apps.message,
        "scroll_count": apps.scroll_count,
        "history": [state.value for state in apps.history],
        "visible_text": (apps.snapshot.visible_text[:30] if apps.snapshot else []),
    })

    success = apps.success
    events.append({
        "event": "SUCCESS" if success else "FAILURE",
        "message": "Adaptive controller completed Bluetooth -> Back -> App Management." if success else "Adaptive controller did not complete the bounded sequence.",
    })
    print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
