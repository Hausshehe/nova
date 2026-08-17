import re

from tools.android_root import run_root


def click_text(text):
    """Click a visible Android UI element by its text/content description.

    The result reflects the accessibility service's actual click result, not
    merely whether Android accepted the broadcast.
    """
    if not text or not str(text).strip():
        return {"success": False, "verified": False, "error": "Text cannot be empty"}

    target = str(text).strip()
    command = (
        "/system/bin/am broadcast "
        "-n com.infoney.nova/.NovaClickReceiver "
        "-a com.infoney.nova.CLICK_TEXT "
        "--es text "
        + "'" + target.replace("'", "'\\''") + "'"
    )

    try:
        result = run_root(command, timeout=8)
        output = (result.stdout or "").strip()
        error = (result.stderr or "").strip()

        if result.returncode != 0:
            return {
                "success": False,
                "verified": False,
                "target": target,
                "error": error or output,
                "returncode": result.returncode,
            }

        match = re.search(r"Broadcast completed: result=(-?\d+)", output)
        action_result = bool(match and int(match.group(1)) == 1)
        return {
            "success": action_result,
            "verified": action_result,
            "target": target,
            "output": output,
            "message": (
                "Accessibility service confirmed the click."
                if action_result
                else "Broadcast delivered, but the accessibility service did not confirm the click."
            ),
        }
    except Exception as e:
        return {"success": False, "verified": False, "target": target, "error": str(e)}
