import subprocess
import re

def find_android_app(app_name):
    try:
        result = subprocess.run(
            ["pm", "list", "packages"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {
                "success": False,
                "verified": False,
                "message": f"pm failed: {result.stderr.strip() or 'unknown error'}"
            }

        query = app_name.lower().strip()

        packages = []
        for line in result.stdout.splitlines():
            line = line.strip()

            if not line.startswith("package:"):
                continue

            package = line[8:].strip()

            if query in package.lower():
                packages.append(package)

        if not packages:
            return {
                "success": False,
                "verified": True,
                "message": f"No installed Android package matched '{app_name}'."
            }

        return {
            "success": True,
            "verified": True,
            "packages": packages,
            "message": f"Found {len(packages)} matching package(s)."
        }

    except Exception as e:
        return {
            "success": False,
            "verified": False,
            "message": str(e)
        }
