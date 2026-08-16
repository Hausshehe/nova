import subprocess
import json

def volume_control(action, stream="music", level=None):
    try:
        volumes = subprocess.check_output(["termux-volume"]).decode("utf-8")
        volumes = json.loads(volumes)
        volume_stream = next((v for v in volumes if v["stream"] == stream), None)
        if volume_stream is None:
            return {
                "success": False,
                "verified": False,
                "message": f"Stream '{stream}' not found"
            }
        if action == "up":
            new_level = volume_stream["volume"] + 1
            if new_level > volume_stream["max_volume"]:
                return {
                    "success": False,
                    "verified": False,
                    "message": f"Cannot increase volume beyond {volume_stream['max_volume']}"
                }
            subprocess.check_call(["termux-volume", stream, str(new_level)])
            volumes = subprocess.check_output(["termux-volume"]).decode("utf-8")
            volumes = json.loads(volumes)
            volume_stream = next((v for v in volumes if v["stream"] == stream), None)
            if volume_stream["volume"] != new_level:
                return {
                    "success": False,
                    "verified": False,
                    "message": f"Failed to increase volume to {new_level}"
                }
            return {
                "success": True,
                "verified": True,
                "message": f"Volume increased to {new_level}"
            }
        elif action == "down":
            new_level = volume_stream["volume"] - 1
            if new_level < 0:
                return {
                    "success": False,
                    "verified": False,
                    "message": f"Cannot decrease volume below 0"
                }
            subprocess.check_call(["termux-volume", stream, str(new_level)])
            volumes = subprocess.check_output(["termux-volume"]).decode("utf-8")
            volumes = json.loads(volumes)
            volume_stream = next((v for v in volumes if v["stream"] == stream), None)
            if volume_stream["volume"] != new_level:
                return {
                    "success": False,
                    "verified": False,
                    "message": f"Failed to decrease volume to {new_level}"
                }
            return {
                "success": True,
                "verified": True,
                "message": f"Volume decreased to {new_level}"
            }
        elif action == "set":
            if level is None:
                return {
                    "success": False,
                    "verified": False,
                    "message": "Level must be provided for 'set' action"
                }
            if level < 0 or level > volume_stream["max_volume"]:
                return {
                    "success": False,
                    "verified": False,
                    "message": f"Level must be between 0 and {volume_stream['max_volume']}"
                }
            subprocess.check_call(["termux-volume", stream, str(level)])
            volumes = subprocess.check_output(["termux-volume"]).decode("utf-8")
            volumes = json.loads(volumes)
            volume_stream = next((v for v in volumes if v["stream"] == stream), None)
            if volume_stream["volume"] != level:
                return {
                    "success": False,
                    "verified": False,
                    "message": f"Failed to set volume to {level}"
                }
            return {
                "success": True,
                "verified": True,
                "message": f"Volume set to {level}"
            }
        else:
            return {
                "success": False,
                "verified": False,
                "message": f"Invalid action '{action}'"
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
            "message": f"Failed to parse JSON: {e}"
        }