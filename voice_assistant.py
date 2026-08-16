import subprocess
import requests
import json

API_URL = "http://127.0.0.1:8080/v1/chat/completions"

SYSTEM_PROMPT = open(
    "/data/data/com.termux/files/home/infoney/infoney_prompt.txt",
    encoding="utf-8"
).read()

print("🤖 Infoney is ready.")
print("🎙️ Say something...")

while True:
    try:
        result = subprocess.run(
            ["termux-speech-to-text"],
            capture_output=True,
            text=True
        )

        user_text = result.stdout.strip()

        if not user_text:
            print("🎙️ I didn't hear anything.")
            continue

        print("You:", user_text)

        # Recognize common speech-recognition mistakes for "Infoney"
        replacements = {
            "in funny": "Infoney",
            "in Forney": "Infoney",
            "Anthony": "Infoney",
            "Forney": "Infoney",
        }

        for wrong, correct in replacements.items():
            user_text = user_text.replace(wrong, correct)

        if "infoney stop" in user_text.lower():
            print("🤖 Goodbye, Zanyar.")
            subprocess.run([
                "termux-tts-speak",
                "Goodbye Zanyar."
            ])
            break

        response = requests.post(
            API_URL,
            json={
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": user_text
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 300
            },
            timeout=120
        )

        data = response.json()

        if response.status_code != 200:
            print("AI error:", data)
            continue

        answer = data["choices"][0]["message"]["content"].strip()

        print("Infoney:", answer)

        subprocess.run([
            "termux-tts-speak",
            answer
        ])

    except KeyboardInterrupt:
        print("\n🤖 Infoney stopped.")
        break

    except Exception as e:
        print("Error:", e)
