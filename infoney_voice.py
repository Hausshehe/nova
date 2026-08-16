import os
import json
import requests
import subprocess

from tools.executor import execute_tool
from tools.registry import discover_tools


API_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = open(
    "/data/data/com.termux/files/home/infoney/infoney_prompt.txt",
    encoding="utf-8"
).read()


messages = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT
    }
]


# =========================================================
# TOOLS
# =========================================================

import inspect



INTERNAL_TOOLS = {
    "executor",
    "registry",
    "approval",
    "installer",
    "self_builder",
    "self_improve",
    "ai_builder",
    "proposal_tester"
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

    # Infer type from the default value.
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

    # Useful inference for common tool parameters.
    if parameter_name in {
        "level",
        "volume",
        "brightness",
        "percentage",
        "amount",
        "value"
    }:
        return "number"

    return "string"


def build_tool_definitions():

    tool_definitions = []

    discovered = discover_tools()

    for name, module in discovered.items():

        if name in INTERNAL_TOOLS:
            continue

        function = getattr(module, name, None)

        if function is None:
            continue

        signature = inspect.signature(function)

        properties = {}
        required = []

        for parameter_name, parameter in signature.parameters.items():

            if parameter.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD
            ):
                continue

            parameter_type = get_parameter_type(
                parameter_name,
                parameter
            )

            property_definition = {
                "type": parameter_type,
                "description": (
                    f"Parameter '{parameter_name}' "
                    f"for {name}."
                )
            }

            if name == "volume_control" and parameter_name == "action":
                property_definition["enum"] = [
                    "up",
                    "down",
                    "set"
                ]

            properties[parameter_name] = property_definition

            if parameter.default is inspect.Parameter.empty:
                required.append(parameter_name)

        tool_definitions.append({
            "type": "function",
            "function": {
                "name": name,
                "description": f"Use the {name} tool.",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        })

    tool_definitions.append({
        "type": "function",
        "function": {
            "name": "open_mt5",
            "description": (
                "Open the MetaTrader 5 Android application."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    })

    return tool_definitions
TOOLS = build_tool_definitions()

# =========================================================
# VOICE
# =========================================================

def speak(text):
    if not text:
        return

    subprocess.run([
        "termux-tts-speak",
        "-l", "en",
        text
    ])


def listen():
    print("🎙️ Listening...")

    result = subprocess.run(
        ["termux-speech-to-text"],
        capture_output=True,
        text=True
    )

    return result.stdout.strip()


# =========================================================
# TEXT CLEANING
# =========================================================

def clean_text(text):

    replacements = {
        "novel": "Nova",
        "Nora": "Nova",
        "Noah": "Nova",
        "Novah": "Nova",
        "Nova Nova": "Nova",
        "nova nova": "Nova"
    }

    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)

    return text.strip()


# =========================================================
# MT5
# =========================================================

def open_mt5():

    result = subprocess.run(
        [
            "am",
            "start",
            "-n",
            "net.metaquotes.metatrader5/"
            "net.metaquotes.metatrader5.ui.MainActivity"
        ],
        capture_output=True,
        text=True
    )

    return result.returncode == 0


# =========================================================
# TOOL EXECUTION
# =========================================================

def execute_requested_tool(function_name, arguments):
    # Groq may return null/None for tools with no arguments.
    if arguments is None:
        arguments = {}

    if function_name == "open_mt5":
        success = open_mt5()

        return {
            "success": success,
            "result": (
                "MetaTrader 5 opened."
                if success
                else "Failed to open MetaTrader 5."
            )
        }

    discovered = discover_tools()

    if function_name not in discovered:
        return {
            "success": False,
            "error": f"Unknown tool: {function_name}"
        }

    module = discovered[function_name]

    function = getattr(
        module,
        function_name,
        None
    )

    if function is None:
        return {
            "success": False,
            "error": (
                f"Tool '{function_name}' "
                "has no matching function."
            )
        }

    try:
        return execute_tool(
            function_name,
            function_name,
            **arguments
        )

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# =========================================================
# GROQ
# =========================================================


# =========================================================

def ask_nova(user_text):

    messages.append({
        "role": "user",
        "content": user_text
    })

    print("🧠 Thinking...")

    response = requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer " + os.environ["GROQ_API_KEY"],
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "tools": build_tool_definitions(),
            "tool_choice": "auto",
            "temperature": 0.4,
            "max_tokens": 300
        },
        timeout=30
    )

    if response.status_code != 200:

        print("❌ Groq error:", response.text)

        messages.pop()

        return None

    data = response.json()

    message = data["choices"][0]["message"]


    # -----------------------------------------------------
    # TOOL CALL
    # -----------------------------------------------------

    if "tool_calls" in message:

        messages.append(message)

        for tool_call in message["tool_calls"]:

            function_name = tool_call["function"]["name"]

            try:
                arguments = json.loads(
                    tool_call["function"]["arguments"]
                )
            except Exception:
                arguments = {}

            print("🔧 Tool:", function_name)
            print("📦 Arguments:", arguments)

            result = execute_requested_tool(
                function_name,
                arguments
            )

            print("⚙️ Result:", result)


            # Send tool result back to Groq
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(result)
            })


        # Tool execution has already happened.
        # Tell Nova explicitly to trust the actual tool result.

        messages.append({
            "role": "system",
            "content": (
                "IMPORTANT: The requested tools have already been executed. "
                "Treat their returned results as authoritative. "
                "If a tool returned success=true, NEVER claim that you "
                "cannot perform the action or lack the ability to do it. "
                "Instead, clearly report that the action succeeded. "
                "If a tool returned success=false, honestly report the failure. "
                "Do not contradict the actual tool result."
            )
        })

        # Ask Nova for the final response.
        follow_up = requests.post(
            API_URL,
            headers={
                "Authorization": "Bearer " + os.environ["GROQ_API_KEY"],
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 150
            },
            timeout=30
        )

        if follow_up.status_code != 200:
            print("❌ Groq follow-up error:",
                  follow_up.text)
            return None

        final_data = follow_up.json()

        answer = (
            final_data["choices"][0]["message"]
            ["content"]
            .strip()
        )

        messages.append({
            "role": "assistant",
            "content": answer
        })

        return answer


    # -----------------------------------------------------
    # NORMAL RESPONSE
    # -----------------------------------------------------

    answer = message["content"].strip()

    messages.append({
        "role": "assistant",
        "content": answer
    })

    return answer



# =========================================================
# SELF-TEACHING
# =========================================================

def voice_approval():
    speak("I have created and tested the tool. Do you want me to install it?")
    print("🎙️ Waiting for approval...")

    answer = listen().lower().strip()

    yes_words = {
        "yes",
        "yeah",
        "yep",
        "sure",
        "okay",
        "ok",
        "install it",
        "go ahead",
        "do it"
    }

    no_words = {
        "no",
        "nope",
        "cancel",
        "don't",
        "do not"
    }

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

    # Convert the capability description into a stable tool name.
    # We deliberately remove conversational words such as
    # "how", "to", "the", and "my".
    stop_words = {
        "how",
        "to",
        "the",
        "a",
        "an",
        "my",
        "me",
        "please",
        "can",
        "you",
        "yourself"
    }

    words = [
        word.lower()
        for word in description.replace("-", " ").split()
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

    result = teach_self(
        tool_name,
        description
    )

    print("🧪 Teaching result:", result)

    if not result.get("success"):
        answer = (
            "I couldn't learn that. "
            + result.get("message", "The proposal failed.")
        )
        print("🤖 Nova:", answer)
        speak(answer)
        return True

    approval = request_approval(
        tool_name,
        approval_callback=voice_approval
    )

    print("🔐 Approval result:", approval)

    if approval.get("success"):
        global TOOLS
        TOOLS = build_tool_definitions()

        answer = (
            f"I learned {tool_name} "
            "and installed it successfully."
        )
    else:
        answer = (
            "I created and tested the tool, "
            "but I did not install it."
        )

    print("🤖 Nova:", answer)
    speak(answer)

    return True


# =========================================================
# MAIN
# =========================================================
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


            # -------------------------------------------------
            # NOVA WAKE / GREETING
            # -------------------------------------------------

            if lower_text in [
                "nova",
                "hey nova",
                "hello nova",
                "hi nova"
            ]:

                answer = "Yes, Zanyar?"

                print("🤖 Nova:", answer)

                speak(answer)

                continue


            # -------------------------------------------------
            # STOP
            # -------------------------------------------------

            if "nova stop" in lower_text:

                answer = "Goodbye, Zanyar."

                print("🤖 Nova:", answer)

                speak(answer)

                break


            # -------------------------------------------------
            # AI + TOOLS
            # -------------------------------------------------

            # -------------------------------------------------
            # SELF-TEACHING
            # -------------------------------------------------
            handled = teach_from_voice(user_text)

            if handled:
                continue

            # -------------------------------------------------
            # AI + TOOLS
            # -------------------------------------------------
            answer = ask_nova(user_text)


            if answer:

                print("🤖 Nova:", answer)

                # Keep action commands silent when appropriate.
                # Groq will normally produce a short confirmation.
                speak(answer)


        except KeyboardInterrupt:

            print("\n🤖 Nova stopped.")

            break


        except Exception as e:

            print("❌ Error:", e)
