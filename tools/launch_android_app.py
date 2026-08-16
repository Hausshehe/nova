"""Launch an installed Android application by package name."""

import re
import subprocess


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
        process = subprocess.run(
            [
                "su",
                "-c",
                "/system/bin/am start -a android.intent.action.MAIN "
                "-c android.intent.category.LAUNCHER -p " + package,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

        output = (process.stdout + "\n" + process.stderr).strip()

        if process.returncode != 0:
            return {
                "success": False,
                "verified": False,
                "package": package,
                "message": output or "Android launch command failed.",
            }

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
