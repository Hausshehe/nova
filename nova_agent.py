"""Nova's goal-driven Android agent loop."""

import inspect
import json
import os
import requests

from tools.executor import execute_tool
from tools.registry import discover_tools


API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
MAX_STEPS = 12

AGENT_TOOLS = {
    "observe_android",
    "find_android_app",
    "launch_android_app",
    "click_text",
    "type_text",
}


SYSTEM_PROMPT = """
You are Nova's Android agent.

Accomplish the user's goal on the Android phone. Treat every request as a
new goal. Do not depend on hard-coded app-specific procedures, coordinates,
or command names.

Rules:
1. Observe the current Android UI before deciding what to do.
2. Use generic capabilities as building blocks and compose them dynamically.
3. After every state-changing action, observe the resulting UI before taking
   another action or claiming success.
4. If the UI differs from expectations, re-plan from the new state.
5. Use visible text, content descriptions, resource IDs, and package identity;
   never assume fixed coordinates.
6. Do not invent package names or UI elements. Discover them.
7. Do not claim success merely because a command returned successfully.
8. For destructive, privacy-sensitive, financial, or otherwise consequential
   final actions, ask for confirmation before performing that final action.
9. If the available primitives cannot accomplish the goal, say what capability
   is missing instead of pretending.

Available primitives:
- observe_android: inspect the current Android UI.
- find_android_app: discover installed package names from a human app name.
- launch_android_app: launch a discovered Android package.
- click_text: click a visible UI element by text/content description.
- type_text: type into the currently focused input field.

There is intentionally no tool named clear_chrome_data, block_facebook, or
open_spotify. Solve those goals through observation, discovery, reasoning, and
generic actions.
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

    for name in sorted(AGENT_TOOLS):
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

        definitions.append({
            "type": "function",
            "function": {
                "name": name,
                "description": inspect.getdoc(function) or f"Use {name}.",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        })

    return definitions


def _call_groq(messages):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set.")

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 700,
        "tools": build_agent_tool_definitions(),
        "tool_choice": "auto",
        "parallel_tool_calls": False,
    }

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

    data = response.json()
    return data["choices"][0]["message"]


def _tool_result_message(tool_call, result):
    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(result, ensure_ascii=False),
    }


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
    observed_after_action = False

    for step in range(1, MAX_STEPS + 1):
        message = _call_groq(messages)
        messages.append(message)
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            answer = (message.get("content") or "").strip()

            if action_seen and not observed_after_action:
                messages.append({
                    "role": "system",
                    "content": (
                        "A state-changing action occurred but the resulting "
                        "state has not been observed yet. Call observe_android "
                        "before claiming the user's goal is complete."
                    ),
                })
                continue

            return {"success": True, "message": answer, "steps": step}

        # Execute only the first call from each model turn so Nova always gets
        # a chance to observe the real device before choosing another action.
        tool_call = tool_calls[0]
        function = tool_call.get("function") or {}
        function_name = function.get("name", "")
        raw_arguments = function.get("arguments") or "{}"

        result = None
        try:
            arguments = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be a JSON object.")
        except (json.JSONDecodeError, ValueError) as exc:
            result = {
                "success": False,
                "verified": False,
                "message": f"Invalid tool arguments: {exc}",
            }
            arguments = {}

        if result is None:
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
                observed_after_action = bool(result.get("success"))
        else:
            action_seen = True
            observed_after_action = False

        messages.append(_tool_result_message(tool_call, result))

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
