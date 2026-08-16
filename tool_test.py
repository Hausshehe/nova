import os
import json
import requests

from tools.executor import execute_tool


API_URL = "https://api.groq.com/openai/v1/chat/completions"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "flashlight",
            "description": "Turn the phone flashlight on or off.",
            "parameters": {
                "type": "object",
                "properties": {
                    "on": {
                        "type": "boolean",
                        "description": "True to turn the flashlight on, false to turn it off."
                    }
                },
                "required": ["on"]
            }
        }
    }
]


def ask_nova(user_text):
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
                    "content": (
                        "You are Nova, a personal AI assistant. "
                        "When the user asks you to control the flashlight, "
                        "use the flashlight tool. "
                        "For anything else, answer normally."
                    )
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0.2,
            "max_tokens": 200
        },
        timeout=30
    )

    if response.status_code != 200:
        print("Groq error:")
        print(response.text)
        return

    data = response.json()

    message = data["choices"][0]["message"]

    # AI wants to use a tool
    if "tool_calls" in message:

        for tool_call in message["tool_calls"]:

            function_name = tool_call["function"]["name"]

            arguments = json.loads(
                tool_call["function"]["arguments"]
            )

            print("🔧 Tool:", function_name)
            print("📦 Arguments:", arguments)

            result = execute_tool(
                "flashlight",
                function_name,
                **arguments
            )

            print("⚙️ Result:", result)

            if result["success"]:
                print("🤖 Nova: Done.")
            else:
                print("🤖 Nova: I couldn't complete that action.")

        return

    # Normal AI response
    print("🤖 Nova:", message["content"])


print("🤖 Nova tool test")
print("Type a command.")
print("Type 'exit' to stop.")

while True:

    user_text = input("\nYou: ").strip()

    if user_text.lower() == "exit":
        break

    if not user_text:
        continue

    ask_nova(user_text)
