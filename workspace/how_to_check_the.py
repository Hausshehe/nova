import json
import subprocess

def how_to_check_the():
    try:
        output = subprocess.check_output(
            ["termux-battery-status"],
            stderr=subprocess.STDOUT
        ).decode('utf-8')
        battery_status = json.loads(output)
        return {
            'success': True,
            'verified': True,
            'message': battery_status
        }
    except subprocess.CalledProcessError as e:
        return {
            'success': False,
            'verified': False,
            'message': f"Failed to check battery status: {e.output.decode('utf-8')}"
        }
    except json.JSONDecodeError as e:
        return {
            'success': False,
            'verified': False,
            'message': f"Failed to parse battery status JSON: {e}"
        }