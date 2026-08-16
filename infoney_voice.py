import os
import json
import requests
import subprocess
import inspect

from tools.executor import execute_tool
from tools.registry import discover_tools

API_URL = "https://api.groq.com/openai/v1/chat/completions"
SYSTEM_PROMPT = open(
    "/data/data/com.termux/files/home/infoney/infoney_prompt.txt",
    encoding="utf-8"
).read()

messages = [{"role": "system", "content": SYSTEM_PROMPT}]
MAX_HISTORY_MESSAGES = 8

INTERNAL_TOOLS = {
    "executor", "registry", "approval", "installer", "self_builder",
    "self_improve", "ai_builder", "proposal_tester"
}


def get_parameter_type(parameter_name, parameter):
    annotation = parameter.annotation
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is str:
        return "string"
    if parameter.default is not inspect.Parameter.empty:
        default = parameter.default
        if isinstance(default, bool):
            return "boolean"
        if isinstance(default, int):
            return "integer"
        if isinstance(default, float):
            return "number"
        if isinstance(default, str):
            return "string"
    if parameter_name in {"level", "volume", "brightness", "percentage", "amount", "value"}:
        return "number"
    return "string"


def build_tool_definitions():
    definitions = []
    for name, module in discover_tools().items():
        if name in INTERNAL_TOOLS:
            continue
        function = getattr(module, name, None)
        if function is None:
            continue
        properties = {}
        required = []
        for parameter_name, parameter in inspect.signature(function).parameters.items():
            if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            properties[parameter_name] = {
                "type": get_parameter_type(parameter_name, parameter),
                "description": f"Parameter '{parameter_name}' for {name}."
            }
            if name == "volume_control" and parameter_name == "action":
                properties[parameter_name]["enum"] = ["up", "down", "set"]
            if parameter.default is inspect.Parameter.empty:
                required.append(parameter_name)
        definitions.append({
            "type": "function",
            "function": {
                "name": name,
                "description": f"Use the {name} tool.",
                "parameters": {"type": "object", "properties": properties, "required": required}
            }
        })
    definitions.append({
        "type": "function",
        "function": {
            "name": "open_mt5",
            "description": "Open the MetaTrader 5 Android application.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    })
    return definitions


TOOLS = build_tool_definitions()


def speak(text):
    if text:
        subprocess.run(["termux-tts-speak", "-l", "en", text])


def listen():
    print("🎙️ Listening...")
    result = subprocess.run(["termux-speech-to-text"], capture_output=True, text=True)
    return result.stdout.strip()


def clean_text(text):
    replacements = {
        "novel": "Nova", "Nora": "Nova", "Noah": "Nova",
        "Novah": "Nova", "Nova Nova": "Nova", "nova nova": "Nova"
    }
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    return text.strip()


def open_mt5():
    result = subprocess.run(
        ["am", "start", "-n", "net.metaquotes.metatrader5/net.metaquotes.metatrader5.ui.MainActivity"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def execute_requested_tool(function_name, arguments):
    arguments = arguments or {}
    if function_name == "open_mt5":
        success = open_mt5()
        return {"success": success, "result": "MetaTrader 5 opened." if success else "Failed to open MetaTrader 5."}

    discovered = discover_tools()
    if function_name not in discovered:
        return {"success": False, "error": f"Unknown tool: {function_name}"}

    function = getattr(discovered[function_name], function_name, None)
    if function is None:
        return {"success": False, "error": f"Tool '{function_name}' has no matching function."}

    try:
        return execute_tool(function_name, function_name, **arguments)
    except Exception as e:
        return {"success": False, "error": str(e)}


def _trim_history():
    global messages
    if len(messages) > MAX_HISTORY_MESSAGES + 1:
        messages = [messages[0]] + messages[-MAX_HISTORY_MESSAGES:]


def _compact_tool_confirmation(tool_calls, results):
    """Create a useful confirmation without spending another Groq request."""
    for result in results:
        if not result.get("success"):
            error = result.get("error") or result.get("message") or "The tool failed."
            return f"I couldn't complete that: {error}"

    if len(tool_calls) == 1 and len(results) == 1:
        name = tool_calls[0]["function"]["name"]
        result = results[0]

        # Prefer the tool's own human-readable result when it is specific.
        detail = result.get("result")
        if isinstance(detail, str) and detail.strip() and detail.strip().lower() not in {"done", "success", "true"}:
            return detail.strip()

        friendly = {
            "open_spotify": "Spotify is open.",
            "open_mt5": "MetaTrader 5 is open.",
            "open_calculator": "The calculator is open.",
            "open_camera": "The camera is open.",
            "open_settings": "Settings are open.",
            "open_youtube": "YouTube is open.",
            "open_chrome": "Chrome is open.",
            "open_browser": "The browser is open.",
            "flashlight": "Done — the flashlight has been updated.",
            "volume_control": "Done — the volume has been updated.",
        }
        if name in friendly:
            return friendly[name]

    if len(tool_calls) > 1:
        return "Done — I completed the requested actions."
    return "Done."


def _groq_request(payload):
    return requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer " + os.environ["GROQ_API_KEY"],
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=30
    )


def ask_nova(user_text):
    global messages
    messages.append({"role": "user", "content": user_text})
    _trim_history()
    print("🧠 Thinking...")

    response = _groq_request({
        "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "messages": messages,
        "tools": build_tool_definitions(),
        "tool_choice": "auto",
        "temperature": 0.4,
        "max_tokens": 300
    })

    if response.status_code != 200:
        print("❌ Groq error:", response.text)
        if messages and messages[-1].get("role") == "user":
            messages.pop()
        return None

    message = response.json()["choices"][0]["message"]

    if "tool_calls" in message and message["tool_calls"]:
        messages.append(message)
        results = []

        for tool_call in message["tool_calls"]:
            function_name = tool_call["function"]["name"]
            try:
                arguments = json.loads(tool_call["function"]["arguments"] or "{}")
            except Exception:
                arguments = {}

            print("🔧 Tool:", function_name)
            print("📦 Arguments:", arguments)
            result = execute_requested_tool(function_name, arguments)
            print("⚙️ Result:", result)
            results.append(result)

        answer = _compact_tool_confirmation(message["tool_calls"], results)
        messages.append({"role": "assistant", "content": answer})
        _trim_history()
        return answer

    answer = (message.get("content") or "").strip()
    messages.append({"role": "assistant", "content": answer})
    _trim_history()
    return answer


def voice_approval():
    speak("I have created and tested the tool. Do you want me to install it?")
    print("🎙️ Waiting for approval...")
    answer = listen().lower().strip()
    yes_words = {"yes", "yeah", "yep", "sure", "okay", "ok", "install it", "go ahead", "do it"}
    no_words = {"no", "nope", "cancel", "don't", "do not"}
    if any(word in answer for word in yes_words):
        return "y"
    if any(word in answer for word in no_words):
        return "n"
    speak("I didn't understand. I will not install the tool.")
    return "n"


def teach_from_voice(user_text):
    from tools.teach_self import teach_self
    from tools.approval import request_approval

    lower = user_text.lower().strip()
    trigger = "teach yourself"
    if trigger not in lower:
        return None

    description = lower.split(trigger, 1)[1].strip()
    if not description:
        answer = "What would you like me to teach myself?"
        print("🤖 Nova:", answer)
        speak(answer)
        return True

    stop_words = {"how", "to", "the", "a", "an", "my", "me", "please", "can", "you", "yourself"}
    words = [
        word.lower() for word in description.replace("-", " ").split()
        if word.isalnum() and word.lower() not in stop_words
    ]
    if not words:
        answer = "I couldn't determine what capability to learn."
        print("🤖 Nova:", answer)
        speak(answer)
        return True

    tool_name = "_".join(words[:5]).strip("_")
    print("\n🧠 Self-teaching request")
    print("Tool:", tool_name)
    print("Capability:", description)

    result = teach_self(tool_name, description)
    print("🧪 Teaching result:", result)
    if not result.get("success"):
        answer = "I couldn't learn that. " + result.get("message", "The proposal failed.")
        print("🤖 Nova:", answer)
        speak(answer)
        return True

    approval = request_approval(tool_name, approval_callback=voice_approval)
    print("🔐 Approval result:", approval)

    if approval.get("success"):
        global TOOLS
        TOOLS = build_tool_definitions()
        answer = f"I learned {tool_name} and installed it successfully."
    else:
        answer = "I created and tested the tool, but I did not install it."

    print("🤖 Nova:", answer)
    speak(answer)
    return True


if __name__ == "__main__":
    print("🤖 Nova is ready!")
    print("Press Enter when you want to speak.")
    print("Type 'exit' to stop.")

    while True:
        try:
            command = input("\n👉 ")
            if command.lower().strip() == "exit":
                speak("Goodbye, Zanyar.")
                break

            user_text = listen()
            if not user_text:
                print("❌ I didn't hear anything.")
                continue

            user_text = clean_text(user_text)
            print("You:", user_text)
            lower_text = user_text.lower().strip()

            if lower_text in {"nova", "hey nova", "hello nova", "hi nova"}:
                answer = "Yes, Zanyar?"
                print("🤖 Nova:", answer)
                speak(answer)
                continue

            if "nova stop" in lower_text:
                answer = "Goodbye, Zanyar."
                print("🤖 Nova:", answer)
                speak(answer)
                break

            handled = teach_from_voice(user_text)
            if handled:
                continue

            answer = ask_nova(user_text)
            if answer:
                print("🤖 Nova:", answer)
                speak(answer)

        except KeyboardInterrupt:
            print("\n🤖 Nova stopped.")
            break
        except Exception as e:
            print("❌ Error:", e)
