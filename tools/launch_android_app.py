"""Launch an installed Android application by discovered package name."""

import re

from tools.android_root import run_root


_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")


def launch_android_app(package):
    """Launch an installed Android application by its discovered package name."""
    package = str(package or "").strip()

    if not package or not _PACKAGE_RE.fullmatch(package):
        return {
            "success": False,
            "verified": False,
            "message": "Invalid Android package name.",
        }

    try:
        result = run_root(
            "/system/bin/am start -a android.intent.action.MAIN "
            "-c android.intent.category.LAUNCHER -p " + package
        )
        output = result.stdout.strip()
        return {
            "success": True,
            "verified": False,
            "package": package,
            "message": "Android launch command completed; verify the resulting UI.",
            "output": output,
        }

    except Exception as e:
        return {
            "success": False,
            "verified": False,
            "package": package,
            "message": str(e),
        }
