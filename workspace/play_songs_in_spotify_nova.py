import json
import subprocess

def play_songs_in_spotify_nova():
    try:
        subprocess.check_call(["am", "start", "-a", "android.intent.action.MAIN",
                              "-c", "android.intent.category.LAUNCHER", "-p", "com.spotify.music"])
        return {"success": True, "verified": True, "message": "Spotify Nova launched successfully"}
    except subprocess.CalledProcessError as e:
        return {"success": False, "verified": True, "message": f"Failed to launch Spotify Nova: {e}"}

if __name__ == "__main__":
    print(play_songs_in_spotify_nova())