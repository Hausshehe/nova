import json
import subprocess

def check_battery_in():
    try:
        battery_status = subprocess.check_output(
            ["termux-battery-status"],
            stderr=subprocess.STDOUT
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
            "message": f"Failed to get battery status: {e.output.decode('utf-8')}"
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "verified": True,
            "message": f"Failed to parse battery status JSON: {e}"
        }