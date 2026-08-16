import os
import requests

api_key = os.environ.get("OPENAI_API_KEY")

if not api_key:
    print("API key is not loaded.")
    exit()

response = requests.post(
    "https://api.openai.com/v1/responses",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    json={
        "model": "gpt-5-mini",
        "input": "Hello Infoney! Introduce yourself in one simple sentence."
    },
    timeout=60,
)

print("Status:", response.status_code)
print(response.text)
