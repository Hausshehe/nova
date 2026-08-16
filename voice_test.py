import subprocess

print("🎙️ Infoney is listening...")

result = subprocess.run(
    ["termux-speech-to-text"],
    capture_output=True,
    text=True
)

text = result.stdout.strip()

if text:
    print("You:", text)

    subprocess.run([
        "termux-tts-speak",
        f"You said: {text}"
    ])
else:
    print("I didn't hear anything.")
