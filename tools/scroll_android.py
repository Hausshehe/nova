"""Adaptive Android scrolling without app-specific navigation knowledge."""

import time

from tools.android_root import run_root


SCROLL_SETTLE_SECONDS = 0.75


def _swipe(direction):
    if direction == "down":
        command = "/system/bin/input swipe 540 700 540 300 500"
    else:
        command = "/system/bin/input swipe 540 300 540 700 500"
    return run_root(command)


def scroll_android(direction="down"):
    """Perform one generic scroll and let the planner observe the resulting UI.

    Scrolling itself deliberately does not run a second uiautomator dump. The
    normal observation layer owns UI inspection, so this primitive cannot block
    on a redundant root subprocess or make app-specific assumptions. The
    planner can decide from the fresh observation whether to continue, reverse,
    or take another action.
    """
    requested = str(direction or "down").strip().lower()
    if requested not in {"up", "down"}:
        return {
            "success": False,
            "verified": False,
            "message": "Direction must be 'up' or 'down'.",
        }

    try:
        result = _swipe(requested)
        if result.returncode != 0:
            return {
                "success": False,
                "verified": False,
                "direction": requested,
                "message": (result.stderr or result.stdout or "Scroll failed").strip(),
            }

        # Give Android's scroll animation time to settle before the planner's
        # normal observation call. No extra UI/root probe is performed here.
        time.sleep(SCROLL_SETTLE_SECONDS)

        return {
            "success": True,
            "verified": False,
            "direction": requested,
            "message": "Scroll action completed; observe the current UI to decide the next adaptive action.",
            "output": result.stdout.strip(),
        }
    except Exception as exc:
        return {
            "success": False,
            "verified": False,
            "direction": requested,
            "message": str(exc),
        }
