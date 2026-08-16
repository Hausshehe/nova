"""Nova's goal-driven Android agent loop.

This is the first foundation for adaptive behavior: Nova receives a goal,
observes the current UI, chooses an action from generic capabilities, observes
again, and can re-plan when the state does not match expectations.
"""

import inspect
import json
import os
import requests

from tools.executor import execute_tool
from tools.registry import discover_tools


API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"
MAX_STEPS = 12

# These are primitives, not user commands. The model is expected to compose
# them dynamically to accomplish a goal it has never seen before.
AGENT_TOOLS = {
    "observe_android",
    "find_android_app",
    "launch_android_app",
    "click_text",
    "type_text",
}


SYSTEM_PROMPT = """
You are Nova's Android agent.

Your job is to accomplish the user's GOAL, not to match the request to a
pre-written command.

CORE RULES:

1. Treat every request as a goal that may be completely new.
2. Do not assume a fixed UI path.
3. Use observe_android() to inspect the CURRENT UI before deciding what to do.
4. After an action that changes the UI, observe again.
5. Base the next action on the newest observed state.
6. If the UI differs from what you expected, re-plan instead of repeating
   an old sequence.
7. Use visible text, content descriptions, resource IDs, and UI structure to
   identify controls. Do not use hard-coded screen coordinates.
8. You may compose generic primitives in any order.
9. Never require the user to describe the UI procedure. The user states the
   goal; you determine the procedure.
10. Do not claim an action succeeded merely because a command returned.
    Verify the resulting state with observe_android() whenever possible.
11. If the goal is destructive, privacy-sensitive, financial, or otherwise
    consequential, stop and ask the user for confirmation before performing
    the consequential final action.
12. If the available primitives are insufficient, explain what capability is
    missing instead of pretending.
13. Do not invent UI elements, package names, or Android APIs. Discover them.
14. Prefer the shortest reliable path, but reliability and verification are
    more important than speed.

AVAILABLE PRIMITIVES:
- observe_android: inspect the current Android UI.
- find_android_app: find installed package names matching an app name.
- launch_android_app: launch an installed package.
- click_text: click a visible UI element by text/content description.
- type_text: type into the currently focused input field.

Remember: these are building blocks. There is intentionally no tool named
"clear_chrome_data", "block_facebook", or similar. Solve those goals by
reasoning over the current device state.
"""


def _parameter_type(parameter):
    annotation = parameter.annotation

    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    return "string"


def build_agent_tool_definitions():
    discovered = discover_tools()
    definitions = []

    for name in AGENT_TOOLS:
        module = discovered.get(name)
        if module is None:
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
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            properties[parameter_name] = {
                "type": _parameter_type(parameter),
                "description": f"Input for {name}: {parameter_name}.",
            }

            if parameter.default is inspect.Parameter.empty:
                required.append(parameter_name)

        description = inspect.getdoc(function) or f"Use {name}."

        definitions.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })

    return definitions


def _call_groq(messages, tools=True):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set.")

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 700,
    }

    if tools:
        payload["tools"] = build_agent_tool_definitions()
        payload["tool_choice"] = "auto"

    response = requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=45,
    )

    if response.status_code != 200:
        raise RuntimeError("Groq error: " + response.text)

    return response.json()["choices"][0]["message"]


def run_agent(goal):
    """Run Nova's adaptive goal/action/observation loop for one goal."""
    goal = str(goal or "").strip()
    if not goal:
        return {"success": False, "message": "Goal cannot be empty."}

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Accomplish this goal on the Android phone:\n" + goal,
        },
    ]

    action_seen = False
    verified_after_action = False

    for step in range(1, MAX_STEPS + 1):
        message = _call_groq(messages, tools=True)
        messages.append(message)

        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            answer = (message.get("content") or "").strip()

            if action_seen and not verified_after_action:
                # Do not let the model finish immediately after an action.
                messages.append({
                    "role": "system",
                    "content": (
                        "You performed an action but have not verified its "
                        "result. Call observe_android() now before giving a "
                        "success claim."
                    ),
                })
                continue

            return {
                "success": True,
                "message": answer,
                "steps": step,
            }

        for tool_call in tool_calls:
            function_name = tool_call["function"]["name"]

            try:
                arguments = json.loads(tool_call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}

            if function_name not in AGENT_TOOLS:
                result = {
                    "success": False,
                    "verified": False,
                    "message": "Tool is not available to the adaptive agent.",
                }
            else:
                print(f"🧠 Step {step}: {function_name}({arguments})")
                result = execute_tool(function_name, function_name, **arguments)
                print("⚙️", result)

            if function_name == "observe_android":
                if action_seen:
                    verified_after_action = bool(result.get("success"))
            else:
                action_seen = True
                verified_after_action = False

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })

    return {
        "success": False,
        "message": f"Agent reached the {MAX_STEPS}-step limit without completing the goal.",
        "steps": MAX_STEPS,
    }


if __name__ == "__main__":
    import sys

    goal = " ".join(sys.argv[1:]).strip()
    if not goal:
        print('Usage: python nova_agent.py "your goal"')
        raise SystemExit(2)

    try:
        result = run_agent(goal)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"success": False, "message": str(exc)}, indent=2))
        raise SystemExit(1)
