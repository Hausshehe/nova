import subprocess
import json

def open_spotify():
    try:
        subprocess.check_call(
            ["am", "start", "-a", "android.intent.action.MAIN",
             "-c", "android.intent.category.LAUNCHER", "-p", "com.spotify.music"]
        )
        return {
            "success": True,
            "verified": True,
            "message": "Spotify opened successfully"
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "verified": True,
            "message": f"Failed to open Spotify: {e}"
        }
    except Exception as e:
        return {
            "success": False,
            "verified": False,
            "message": f"An unexpected error occurred: {e}"
        }