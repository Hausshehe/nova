"""Nova's goal-driven Android agent loop."""

import inspect
import json
import os
import requests

from tools.executor import execute_tool
from tools.registry import discover_tools


API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
MAX_STEPS = 16

AGENT_TOOLS = {
    "observe_android",
    "find_android_app",
    "launch_android_app",
    "click_text",
    "click_node",
    "type_text",
    "back_android",
    "scroll_android",
}


SYSTEM_PROMPT = """
You are Nova, a goal-driven Android agent.

The user gives you a GOAL, not a procedure. Your job is to accomplish the goal
on the real Android phone by observing the current state, choosing a generic
action, observing the result, and re-planning as necessary.

FUNDAMENTAL RULES:
1. Every request may be new. Never expect a pre-written command for the goal.
2. Start by observing the current UI unless a tool result already provides the
   exact current state needed for the next decision.
3. Use generic primitives as building blocks. Do not invent app-specific tools.
4. After EVERY state-changing action, call observe_android before choosing the
   next action. Never blindly execute a precomputed sequence.
5. Treat the newest observation as ground truth. If the UI differs from your
   expectation, re-plan from what is actually visible.
6. Identify controls using visible text, content descriptions, resource IDs,
   class/package information, and current UI structure. Never reason from fixed
   screen coordinates.
7. For an app name, discover its installed package dynamically before launching.
8. Do not claim success because a command returned successfully. Verify the
   resulting state against the user's actual goal.
9. You may use back and scrolling when the desired control is not currently
   visible.
10. For destructive, privacy-sensitive, financial, account, or otherwise
    consequential final actions, ask the user for confirmation immediately
    before that consequential action.
11. If a capability is genuinely missing, report the missing primitive instead
    of pretending the task succeeded.
12. Prefer the shortest reliable route, but reliability and verification beat
    speed.

UI INTERACTION:
- observe_android returns a compact semantic state to you and retains the raw
  hierarchy locally for interaction tools. Use visible text, content
  descriptions, resource IDs, packages, classes, bounds/centers, and interactive
  state when selecting controls.
- click_node is the preferred generic interaction when a specific current UI
  node can be identified from semantic attributes.
- Use click_node with a selector such as text, content_description,
  resource_id, class_name, and/or package. It resolves the node against the
  CURRENT hierarchy and calculates its current bounds; never supply guessed
  coordinates.
- click_text remains available as a simpler text/content-description primitive.
- After click_node, click_text, type_text, back_android, scroll_android, or any
  other state-changing action, observe the new UI before acting again.
- If a selector does not match, do not weaken it blindly. Re-observe and reason
  from the new state.

AVAILABLE FUNDAMENTAL PRIMITIVES:
- observe_android: inspect the current Android UI.
- find_android_app: discover installed package names from a human app name.
- launch_android_app: launch a discovered Android package.
- click_node: resolve and tap a current UI node by semantic attributes.
- click_text: activate a visible UI control by its text/content description.
- type_text: enter text into the currently focused input field.
- back_android: press Android Back.
- scroll_android: scroll the current UI up or down.

There is intentionally no tool named open_spotify, clear_chrome_data,
block_facebook, or any other user-goal-specific command. Solve those goals by
reasoning over the current device state with the primitives above.
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
        "max_tokens": 800,
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


def _planner_tool_result(result, function_name):
    """Return the useful planner state without flooding the model with raw XML nodes."""
    if not isinstance(result, dict):
        return result

    if function_name == "observe_android" and result.get("success"):
        return {
            "success": True,
            "verified": bool(result.get("verified")),
            "message": result.get("message", ""),
            "summary": result.get("summary", ""),
            "state": result.get("state", {}),
        }

    if function_name == "click_node":
        # The matched node is useful for audit/debugging, but the planner mainly
        # needs the action result and selector. The next observation is ground truth.
        return {
            "success": bool(result.get("success")),
            "verified": bool(result.get("verified")),
            "selector": result.get("selector"),
            "message": result.get("message", ""),
            "error": result.get("error"),
        }

    return result


def _tool_result_message(tool_call, result, function_name):
    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(
            _planner_tool_result(result, function_name),
            ensure_ascii=False,
        ),
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

        messages.append(_tool_result_message(tool_call, result, function_name))

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
