"""Discover installed Android packages without hard-coded app mappings."""

import subprocess


def find_android_app(app_name):
    """Find installed package names related to a human app name."""
    query = str(app_name or "").lower().strip()

    if not query:
        return {"success": False, "verified": False, "message": "App name cannot be empty."}

    try:
        result = subprocess.run(
            ["su", "-c", "/system/bin/pm list packages"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "verified": False,
                "message": f"Android package manager failed: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}",
            }

        packages = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line.startswith("package:"):
                continue
            package = line[len("package:"):].strip()
            if query in package.lower():
                packages.append(package)

        if not packages:
            return {
                "success": False,
                "verified": True,
                "packages": [],
                "message": f"No installed Android package matched '{app_name}'.",
            }

        return {
            "success": True,
            "verified": True,
            "packages": packages,
            "message": f"Found {len(packages)} matching package(s).",
        }

    except Exception as e:
        return {"success": False, "verified": False, "message": str(e)}
