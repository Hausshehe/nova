import subprocess


def click_text(text):
    """Click a visible Android UI element by its text/content description."""

    if not text or not str(text).strip():
        return {
            "success": False,
            "error": "Text cannot be empty"
        }

    target = str(text).strip()

    # Use the explicit NovaClickReceiver because implicit
    # broadcasts are unreliable on this device.
    command = (
        "/system/bin/am broadcast "
        "-n com.infoney.nova/.NovaClickReceiver "
        "-a com.infoney.nova.CLICK_TEXT "
        "--es text "
        + "'" + target.replace("'", "'\\''") + "'"
        + "\nexit\n"
    )

    try:
        process = subprocess.Popen(
            ["su"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        stdout, stderr = process.communicate(
            command,
            timeout=10
        )

        output = stdout.strip()
        error = stderr.strip()

        if process.returncode != 0:
            return {
                "success": False,
                "target": target,
                "error": error or output,
                "returncode": process.returncode
            }

        return {
            "success": True,
            "target": target,
            "output": output
        }

    except subprocess.TimeoutExpired:
        process.kill()
        return {
            "success": False,
            "target": target,
            "error": "Root shell command timed out"
        }

    except Exception as e:
        return {
            "success": False,
            "target": target,
            "error": str(e)
        }
