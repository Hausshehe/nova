"""Nova's goal-driven Android agent loop.

Nova receives a goal, observes the current device, chooses generic
capabilities, acts, observes again, and re-plans when reality differs from
its expectations. It deliberately contains no app-specific user commands.
"""

import inspect
import json
import os
import requests

from tools.executor import execute_tool
from tools.registry import discover_tools


API_URL = "https://api.groq.com/openai/v1/chat/completions"
# GPT-OSS 120B is currently supported by Groq for local function/tool calling
# and is a better fit for this agent's structured tool-use loop.
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

Your job is to accomplish the user's GOAL, not to match the request to a
pre-written command.

CORE RULES:
1. Every request may be completely new.
2. Never assume a fixed UI path. Android and apps can change.
3. Observe the CURRENT UI before making UI decisions.
4. When an app is named, use find_android_app(name) first. Never invent a
   package name.
5. Perform ONE capability action at a time. After every state-changing action,
   observe again before choosing the next action.
6. Base each next action on the newest device state.
7. If reality differs from expectations, re-plan instead of repeating a script.
8. Use visible text, content descriptions, resource IDs, classes, and state to
   identify controls. Never use fixed screen coordinates.
9. The user states the goal; Nova determines the procedure.
10. Never claim success merely because a command returned successfully.
11. Verification must relate to the user's actual goal. After opening an app,
    for example, verify the resulting foreground package/UI.
12. For destructive, privacy-sensitive, financial, or otherwise consequential
    actions, ask for confirmation before the consequential final action.
13. If the available capabilities are insufficient, say what is missing.
14. Never invent UI elements, package names, or Android APIs.
15. Prefer the shortest reliable route, but prioritize reliability and
    verification over speed.
16. Think about the objective and current device state, not memorized scripts.

AVAILABLE CAPABILITIES:
- observe_android: inspect the current Android UI.
- find_android_app: discover installed package names matching an app name.
- launch_android_app: launch a discovered Android package.
- click_text: click a visible UI element by text/content description.
- type_text: type into the currently focused input field.

There is intentionally no tool named "open_spotify", "clear_chrome_data",
"block_facebook", or similar. Solve those goals using generic capabilities
and the current observed state.
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

    response = requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": messages,
            "tools": build_agent_tool_definitions(),
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_completion_tokens": 1200,
        },
        timeout=60,
    )

    if response.status_code != 200:
        raise RuntimeError("Groq error: " + response.text)

    return response.json()["choices"][0]["message"]


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

        # Execute only the first call from each model turn. This guarantees
        # that Nova sees the real device state before committing to another
        # action, even if a model attempts parallel tool calls.
        tool_call = tool_calls[0]
        function_name = tool_call.get("function", {}).get("name", "")
        raw_arguments = tool_call.get("function", {}).get("arguments") or "{}"

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
        elif function_name not in AGENT_TOOLS:
            result = {
                "success": False,
                "verified": False,
                "message": "Tool is not available to the adaptive agent.",
            }
        else:
            print(f"🧠 Step {step}: {function_name}({arguments})")
            execution = execute_tool(function_name, function_name, **arguments)
            # executor.py wraps the capability result. Preserve that structure
            # so the model receives both the execution status and capability
            # payload.
            result = execution
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
