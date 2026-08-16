import subprocess


def flashlight(on=True):
    command = "on" if on else "off"

    result = subprocess.run(
        ["termux-torch", command],
        capture_output=True,
        text=True
    )

    return result.returncode == 0


if __name__ == "__main__":
    print("Flashlight tool loaded.")
