"""Discover installed Android packages without hard-coded app mappings."""

from tools.android_root import run_root


def _rank_package(package, query):
    """Rank likely launchable app packages above resource/provider packages."""
    package_lower = package.lower()
    query_lower = query.lower()

    score = 0
    if package_lower == query_lower:
        score += 1000

    # Human names such as "settings" commonly match several overlay/provider
    # packages. The actual app package is normally the shortest exact suffix
    # match, while overlays/providers should be strongly deprioritized.
    if package_lower.endswith("." + query_lower):
        score += 500
    if package_lower == "com.android." + query_lower:
        score += 900

    for marker in ("overlay", "resoverlay", "provider", "intelligence", "settingsres"):
        if marker in package_lower:
            score -= 300

    score -= package_lower.count(".")
    score -= len(package_lower) // 100
    return score


def find_android_app(app_name):
    """Find installed package names related to a human app name."""
    query = str(app_name or "").lower().strip()

    if not query:
        return {"success": False, "verified": False, "message": "App name cannot be empty."}

    try:
        result = run_root("/system/bin/pm list packages")
        packages = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line.startswith("package:"):
                continue
            package = line[len("package:"):].strip()
            if query in package.lower():
                packages.append(package)

        packages.sort(key=lambda package: _rank_package(package, query), reverse=True)

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
