import subprocess
import json

def battery_status():
    try:
        output = subprocess.check_output(
            ["termux-battery-status"],
            stderr=subprocess.STDOUT
        )
        battery_info = json.loads(output.decode('utf-8'))
        return {
            'success': True,
            'verified': True,
            'message': battery_info
        }
    except subprocess.CalledProcessError as e:
        return {
            'success': False,
            'verified': False,
            'message': f"Failed to get battery status: {e.output.decode('utf-8')}"
        }
    except json.JSONDecodeError as e:
        return {
            'success': False,
            'verified': False,
            'message': f"Failed to parse battery status: {e}"
        }