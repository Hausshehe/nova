"""Scroll the current Android UI without fixed coordinates in agent code."""

from tools.android_root import run_root


def scroll_android(direction="down"):
    """Scroll the current UI up or down using a generic swipe."""
    direction = str(direction or "down").strip().lower()
    if direction not in {"up", "down"}:
        return {
            "success": False,
            "verified": False,
            "message": "Direction must be 'up' or 'down'.",
        }

    # The coordinates are intentionally confined to this generic primitive;
    # the agent never reasons in screen coordinates. The swipe is centered so
    # it works as a general fallback on normal phone layouts.
    if direction == "down":
        command = "/system/bin/input swipe 540 700 540 300 500"
    else:
        command = "/system/bin/input swipe 540 300 540 700 500"

    try:
        result = run_root(command)
        return {
            "success": True,
            "verified": False,
            "direction": direction,
            "message": "Scroll action sent; observe the UI to verify the result.",
            "output": result.stdout.strip(),
        }
    except Exception as e:
        return {"success": False, "verified": False, "message": str(e)}
