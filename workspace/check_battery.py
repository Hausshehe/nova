import subprocess
import json

def check_battery():
    try:
        battery_status = subprocess.check_output(
            ["termux-battery-status"]
        ).decode("utf-8")
        battery_status = json.loads(battery_status)
        return {
            "success": True,
            "verified": True,
            "message": battery_status
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "verified": True,
            "message": f"Failed to get battery status: {e}"
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "verified": True,
            "message": f"Failed to parse battery status JSON: {e}"
        }