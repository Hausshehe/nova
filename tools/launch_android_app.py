"""Launch an installed Android application by discovered package name."""

import re

from tools.android_root import run_root


_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")


def _resolve_launcher(package):
    """Return the package's default launcher component when Android exposes it."""
    result = run_root(
        "/system/bin/cmd package resolve-activity --brief " + package,
        timeout=5,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        if "/" in line and line.startswith(package + "/"):
            return line
    return ""


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
        component = _resolve_launcher(package)
        if component:
            command = "/system/bin/am start -W -n " + component
        else:
            # Keep the package-based fallback for packages whose launcher
            # component cannot be resolved through cmd package.
            command = (
                "/system/bin/am start -W -a android.intent.action.MAIN "
                "-c android.intent.category.LAUNCHER -p " + package
            )

        result = run_root(command, timeout=10)
        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()

        if result.returncode != 0:
            return {
                "success": False,
                "verified": False,
                "package": package,
                "component": component,
                "message": "Android launch command failed.",
                "output": output,
            }

        return {
            "success": True,
            "verified": False,
            "package": package,
            "component": component,
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
