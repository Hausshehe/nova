"""Press Android's Back action through the shared privileged shell."""

from tools.android_root import run_root


def back_android():
    """Navigate one step backward in the current Android UI."""
    try:
        result = run_root("/system/bin/input keyevent 4")
        return {
            "success": True,
            "verified": False,
            "message": "Android Back action sent; observe the UI to verify the result.",
            "output": result.stdout.strip(),
        }
    except Exception as e:
        return {"success": False, "verified": False, "message": str(e)}
