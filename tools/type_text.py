"""Type text into the currently focused Android input field."""

import subprocess


def type_text(text):
    """Type text into the currently focused Android input field."""
    text = str(text or "")

    if not text:
        return {
            "success": False,
            "verified": False,
            "message": "Text cannot be empty.",
        }

    try:
        # Android's input command treats spaces specially.
        escaped = text.replace(" ", "%s").replace("'", "\\'")

        process = subprocess.run(
            ["su", "-c", "/system/bin/input text '" + escaped + "'"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        output = (process.stdout + "\n" + process.stderr).strip()

        return {
            "success": process.returncode == 0,
            "verified": False,
            "message": (
                "Text input command completed."
                if process.returncode == 0
                else output or "Text input failed."
            ),
        }

    except Exception as e:
        return {
            "success": False,
            "verified": False,
            "message": str(e),
        }
