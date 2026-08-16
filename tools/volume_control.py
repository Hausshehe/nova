import subprocess
import json


def volume_control(action, stream="music", level=None):

    # Normalize natural-language actions.
    action = str(action).lower().strip()

    aliases = {
        "turn up": "up",
        "turn the volume up": "up",
        "increase": "up",
        "increase volume": "up",
        "volume up": "up",
        "louder": "up",

        "turn down": "down",
        "turn the volume down": "down",
        "decrease": "down",
        "decrease volume": "down",
        "volume down": "down",
        "quieter": "down"
    }

    action = aliases.get(action, action)

    try:
        output = subprocess.check_output(
            ["termux-volume"]
        ).decode("utf-8")

        volumes = json.loads(output)

        volume_stream = next(
            (v for v in volumes if v["stream"] == stream),
            None
        )

        if volume_stream is None:
            return {
                "success": False,
                "verified": False,
                "message": f"Stream '{stream}' not found"
            }

        current = volume_stream["volume"]
        maximum = volume_stream["max_volume"]

        if action == "up":

            new_level = min(current + 1, maximum)

            if new_level == current:
                return {
                    "success": True,
                    "verified": True,
                    "message": f"Volume is already at maximum ({maximum})"
                }

        elif action == "down":

            new_level = max(current - 1, 0)

            if new_level == current:
                return {
                    "success": True,
                    "verified": True,
                    "message": "Volume is already at minimum"
                }

        elif action == "set":

            if level is None:
                return {
                    "success": False,
                    "verified": False,
                    "message": "Level must be provided for set action"
                }

            if not isinstance(level, (int, float)):
                return {
                    "success": False,
                    "verified": False,
                    "message": "Level must be numeric"
                }

            if level < 0 or level > maximum:
                return {
                    "success": False,
                    "verified": False,
                    "message": f"Level must be between 0 and {maximum}"
                }

            new_level = int(level)

        else:

            return {
                "success": False,
                "verified": False,
                "message": f"Invalid action '{action}'"
            }

        subprocess.check_call([
            "termux-volume",
            stream,
            str(new_level)
        ])

        output = subprocess.check_output(
            ["termux-volume"]
        ).decode("utf-8")

        volumes = json.loads(output)

        volume_stream = next(
            (v for v in volumes if v["stream"] == stream),
            None
        )

        if volume_stream is None:
            return {
                "success": False,
                "verified": False,
                "message": "Could not verify volume stream"
            }

        actual = volume_stream["volume"]

        if actual != new_level:
            return {
                "success": False,
                "verified": False,
                "message": (
                    f"Volume did not change to {new_level}; "
                    f"actual volume is {actual}"
                )
            }

        return {
            "success": True,
            "verified": True,
            "message": f"Volume set to {actual}"
        }

    except subprocess.CalledProcessError as e:

        return {
            "success": False,
            "verified": False,
            "message": f"Failed to execute command: {e}"
        }

    except json.JSONDecodeError as e:

        return {
            "success": False,
            "verified": False,
            "message": f"Failed to parse volume data: {e}"
        }
