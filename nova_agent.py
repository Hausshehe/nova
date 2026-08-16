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
MODEL = "llama-3.3-70b-versatile"
MAX_STEPS = 12

# Capabilities, not user commands. The model composes these to solve goals
# it has never seen before.
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
2. Never assume a fixed UI path. The UI can change between Android versions,
   app versions, devices, languages, and states.
3. Observe the CURRENT UI before making UI decisions.
4. When the user names an application, do not invent or memorize its package
   name. Use find_android_app(name) first, then launch the discovered package.
5. Perform ONE capability action at a time. After each state-changing action,
   observe again before deciding the next action.
6. Base every next action on the newest observed state.
7. If the UI differs from what you expected, re-plan instead of repeating an
   old sequence.
8. Use visible text, content descriptions, resource IDs, classes, enabled and
   clickable state, and other observed information to identify controls.
9. Do not use hard-coded screen coordinates.
10. Never require the user to describe the UI procedure. The user states the
    goal; Nova determines the procedure.
11. Do not claim an action succeeded merely because a command returned.
    Verify the resulting state whenever possible.
12. Verification must relate to the USER'S GOAL. For example, after opening
    Spotify, confirm that the observed foreground UI/package corresponds to
    Spotify rather than merely confirming that a launch command returned.
13. If a requested action is destructive, privacy-sensitive, financial, or
    otherwise consequential, ask for confirmation before the consequential
    final action.
14. If the available capabilities are insufficient, say what is missing
    instead of pretending the goal was completed.
15. Never invent UI elements, package names, or Android APIs.
16. Prefer the shortest reliable route, but reliability and verification are
    more important than speed.
17. Think in terms of the user's objective and the current device state, not
    previously memorized scripts.

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

        definitions.append({
            "type": "function",
            "function": {
                "name": name,
                "description": inspect.getdoc(function) or f"Use {name}.",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
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
            "temperature": 0.2,
            "max_tokens": 700,
        },
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
        message = _call_groq(messages)
        messages.append(message)
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            answer = (message.get("content") or "").strip()

            if action_seen and not verified_after_action:
                messages.append({
                    "role": "system",
                    "content": (
                        "You performed a state-changing action but have not "
                        "verified the user's goal. Call observe_android() now "
                        "and verify the resulting state before claiming "
                        "success."
                    ),
                })
                continue

            return {"success": True, "message": answer, "steps": step}

        # Execute exactly one tool call per reasoning cycle. This prevents the
        # model from committing to a long blind sequence before seeing how the
        # real device responded to the previous action.
        tool_call = tool_calls[0]
        function_name = tool_call["function"]["name"]

        try:
            arguments = json.loads(
                tool_call["function"].get("arguments") or "{}"
            )
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
                # The observation capability successfully returned a state.
                # The model itself must determine whether that state proves
                # the user's goal, so it gets the full observation result.
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
