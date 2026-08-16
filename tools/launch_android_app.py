"""Launch an installed Android application by package name."""

import subprocess


def launch_android_app(package):
    """Launch the Android launcher activity for an installed package."""
    package = str(package or "").strip()

    if not package:
        return {
            "success": False,
            "verified": False,
            "message": "Package name cannot be empty.",
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
            "verified": True,
            "package": package,
            "message": "Android launch command completed.",
            "output": output,
        }

    except Exception as e:
        return {
            "success": False,
            "verified": False,
            "package": package,
            "message": str(e),
        }
