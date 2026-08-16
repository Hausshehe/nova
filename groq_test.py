import os
import requests

API_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = open(
    "/data/data/com.termux/files/home/infoney/infoney_prompt.txt",
    encoding="utf-8"
).read()

user_text = "Hello Infoney. Introduce yourself to me in simple English."

response = requests.post(
    API_URL,
    headers={
        "Authorization": "Bearer " + os.environ["GROQ_API_KEY"],
        "Content-Type": "application/json"
    },
    json={
        "model": "llama-3.1-8b-instant",
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
        "max_tokens": 200
    },
    timeout=30
)

if response.status_code != 200:
    print("Error:", response.text)
else:
    data = response.json()
    answer = data["choices"][0]["message"]["content"]
    print("Infoney:", answer)
