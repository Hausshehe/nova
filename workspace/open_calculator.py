import subprocess

def open_calculator():
    try:
        subprocess.check_call([
            "am",
            "start",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            "https://www.google.com/search?q=calculator"
        ])

        return {
            "success": True,
            "verified": True,
            "message": "Calculator opened successfully"
        }

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "verified": False,
            "message": f"Failed to open calculator: {e}"
        }

    except Exception as e:
        return {
            "success": False,
            "verified": False,
            "message": f"Unexpected error: {e}"
        }
