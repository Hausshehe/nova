import subprocess
import json

def open_youtube():
    try:
        subprocess.check_call(["am", "start", "-a", "android.intent.action.VIEW", "-d", "https://www.youtube.com"])
        return {
            "success": True,
            "verified": False,
            "message": "YouTube opened successfully"
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "verified": False,
            "message": f"Failed to open YouTube: {e}"
        }