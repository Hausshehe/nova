"""Nova's goal-driven Android agent loop."""

import inspect
import json
import os
import re
import time

import requests

from ai_router import call_ai
from navigation.goal_parser import parse_open_path
from navigation.path import OpenPathNavigator
from tools.executor import execute_tool
from tools.registry import discover_tools


API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
MAX_STEPS = 16
MAX_GROQ_RETRIES = 4
GROQ_BACKOFF_SECONDS = 1.5
MAX_GROQ_RETRY_DELAY = 15.0
MAX_HISTORY_PAIRS = 3
SIMPLE_OPEN_VERIFY_ATTEMPTS = 6
SIMPLE_OPEN_VERIFY_DELAY = 0.75

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

The user gives you a GOAL, not a procedure. Accomplish it on the real Android
phone by observing the current state, choosing a generic action, observing the
result, and re-planning as necessary.

FUNDAMENTAL RULES:
1. Every request may be new. Never expect a pre-written command for the goal.
2. Start by observing the current UI unless the current state is already known.
3. Use generic primitives as building blocks. Do not invent app-specific tools.
4. After EVERY state-changing action, observe the new state before acting again.
5. Treat the newest observation as ground truth and re-plan when it differs.
6. Identify controls semantically: visible text, content descriptions,
   resource IDs, class/package information, and current UI structure.
   Never reason from fixed screen coordinates.
7. Discover an installed package dynamically from a human app name.
8. Never claim success merely because a command returned successfully; verify.
9. Use back and scrolling when needed.
10. For destructive, privacy-sensitive, financial, account, or otherwise
    consequential final actions, ask the user for confirmation immediately
    before that consequential action.
11. If a capability is genuinely missing, report the missing primitive.
12. Prefer the shortest reliable route, but reliability and verification win.
13. foreground_package is authoritative evidence of the current foreground app.
14. Never relaunch an app merely because Termux is where Nova is running.

UI INTERACTION:
- observe_android gives a compact semantic state. Raw hierarchy stays local.
- click_node is preferred when a current UI node can be identified semantically.
- click_node resolves selectors against the CURRENT hierarchy and calculates
  current bounds. Never supply guessed coordinates.
- click_text is available for simple text/content-description activation.
- After any state-changing action, observe before choosing another action.
- If a selector fails, re-observe and reason from the new state.

AVAILABLE PRIMITIVES:
observe_android, find_android_app, launch_android_app, click_node,
click_text, type_text, back_android, scroll_android.

There are intentionally no app-specific goal tools. Solve goals by reasoning
with these generic primitives.
"""


def _parameter_type(parameter):
    annotation = parameter.annotation
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"

    if annotation is inspect.Parameter.empty:
        default = parameter.default
        if isinstance(default, bool):
            return "boolean"
        if isinstance(default, int) and not isinstance(default, bool):
            return "integer"
        if isinstance(default, float):
            return "number"
        if isinstance(default, str):
            return "string"

    annotation_text = str(annotation).lower()
    if "bool" in annotation_text:
        return "boolean"
    if "int" in annotation_text:
        return "integer"
    if "float" in annotation_text:
        return "number"
    return "string"


def build_agent_tool_definitions():
    """Build compact OpenAI-compatible tool schemas for the planner."""
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

            properties[parameter_name] = {"type": _parameter_type(parameter)}
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


def _retry_delay(response, attempt):
    """Use Groq's reset headers when available, but never sleep indefinitely."""
    delay = None

    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            delay = max(0.5, float(retry_after)) + 0.25
        except ValueError:
            pass

    if delay is None:
        reset = response.headers.get("x-ratelimit-reset-tokens")
        if reset:
            match = re.match(r"([0-9.]+)s", reset.strip())
            if match:
                delay = max(0.5, float(match.group(1))) + 0.25

    if delay is None:
        delay = GROQ_BACKOFF_SECONDS * (2 ** attempt)

    return min(delay, MAX_GROQ_RETRY_DELAY)


def _call_groq(messages):
    """Legacy direct Groq call retained for compatibility; new planner uses ai_router."""
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

    for attempt in range(MAX_GROQ_RETRIES):
        response = requests.post(
            API_URL,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=45,
        )

        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]

        if response.status_code == 429 and attempt < MAX_GROQ_RETRIES - 1:
            delay = _retry_delay(response, attempt)
            print(f"⏳ Groq rate limit; retrying in {delay:.1f}s (max {MAX_GROQ_RETRY_DELAY:.0f}s)...")
            time.sleep(delay)
            continue

        if response.status_code >= 500 and attempt < MAX_GROQ_RETRIES - 1:
            delay = GROQ_BACKOFF_SECONDS * (2 ** attempt)
            print(f"⏳ Groq server error; retrying in {delay:.1f}s...")
            time.sleep(delay)
            continue

        raise RuntimeError("Groq error: " + response.text)

    raise RuntimeError("Groq request failed after retries.")


def _unwrap_tool_result(result):
    """Normalize the executor envelope to the actual tool result."""
    if not isinstance(result, dict):
        return result
    if "result" in result and isinstance(result.get("result"), dict):
        return result["result"]
    return result


def _planner_tool_result(result, function_name):
    """Keep planner messages compact while preserving decision-relevant state."""
    result = _unwrap_tool_result(result)
    if not isinstance(result, dict):
        return result

    if function_name == "observe_android" and result.get("success"):
        state = result.get("state") or {}
        foreground_package = result.get("foreground_package") or state.get("foreground_package", "")
        compact_state = {
            "visible_text": state.get("visible_text", []),
            "interactive_labels": [
                node.get("label", "")
                for node in state.get("interactive", [])
                if node.get("label")
            ],
            "scrollable": state.get("scrollable", []),
            "packages": state.get("packages", []),
            "node_count": state.get("node_count", result.get("node_count", 0)),
            "foreground_package": foreground_package,
        }
        return {
            "success": True,
            "verified": bool(result.get("verified")),
            "summary": result.get("summary", ""),
            "state": compact_state,
            "foreground_package": foreground_package,
        }

    if function_name == "click_node":
        return {
            "success": bool(result.get("success")),
            "verified": bool(result.get("verified")),
            "selector": result.get("selector"),
            "message": result.get("message", ""),
            "error": result.get("error"),
        }

    if function_name == "find_android_app":
        return {
            "success": bool(result.get("success")),
            "verified": bool(result.get("verified")),
            "packages": result.get("packages", []),
            "message": result.get("message", ""),
        }

    return result


def _tool_result_message(tool_call, result, function_name):
    planner_result = _planner_tool_result(result, function_name)

    if (
        isinstance(result, dict)
        and "post_action_observation" in result
        and isinstance(planner_result, dict)
    ):
        planner_result["post_action_observation"] = result["post_action_observation"]

    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(
            planner_result,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def _normalize_ui_text(value):
    """Normalize UI labels for semantic, coordinate-free matching."""
    text = str(value or "").strip().lower()
    text = text.replace("‑", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9&+.#' -]", "", text)
    return text.strip()


def _simple_open_goal(goal):
    """Recognize only the narrow generic 'open/launch/start app' goal."""
    normalized = re.sub(r"\s+", " ", str(goal or "").strip().lower())
    match = re.fullmatch(r"(?:open|launch|start)\s+(.+?)(?:\s+app)?", normalized)
    return match.group(1).strip() if match else ""


def _simple_open_path_goal(goal):
    """Recognize any generic multi-stage open path handled by the deterministic navigator."""
    targets = parse_open_path(goal)
    if len(targets) < 2:
        return []
    return targets


def _observe_directly():
    """Observe without spending another planner/AI turn."""
    return _unwrap_tool_result(execute_tool("observe_android", "observe_android"))


def _foreground_from_observation(verification):
    """Extract the authoritative foreground package from an observation."""
    if not isinstance(verification, dict):
        return ""
    foreground = verification.get("foreground_package", "")
    if not foreground:
        foreground = (verification.get("state") or {}).get("foreground_package", "")
    return foreground or ""


def _run_simple_open_goal(app_name):
    """Handle the generic open-app primitive locally, without planner tokens."""
    verification = _observe_directly()
    foreground = _foreground_from_observation(verification)
    if verification.get("success") and foreground and app_name.replace(" ", "") in foreground.lower():
        return {
            "success": True,
            "verified": True,
            "message": f"{app_name} is already open and in the foreground.",
            "steps": 0,
        }

    discovery = _unwrap_tool_result(execute_tool("find_android_app", "find_android_app", app_name=app_name))
    packages = discovery.get("packages") or [] if isinstance(discovery, dict) else []
    if not packages:
        return {
            "success": False,
            "verified": bool(discovery.get("verified")) if isinstance(discovery, dict) else False,
            "message": f"I couldn't find an installed app matching '{app_name}'.",
            "steps": 0,
        }

    if len(packages) != 1:
        return {
            "success": False,
            "verified": bool(discovery.get("verified")) if isinstance(discovery, dict) else False,
            "message": f"The installed-app identity for '{app_name}' is ambiguous; Nova will not guess.",
            "steps": 0,
        }

    package = packages[0]
    launch = _unwrap_tool_result(execute_tool("launch_android_app", "launch_android_app", package=package))
    if not launch.get("success"):
        return {
            "success": False,
            "verified": False,
            "message": launch.get("message", "The app could not be launched."),
            "steps": 0,
        }

    for attempt in range(1, SIMPLE_OPEN_VERIFY_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(SIMPLE_OPEN_VERIFY_DELAY)
        verification = _observe_directly()
        foreground = _foreground_from_observation(verification)
        if verification.get("success") and foreground == package:
            return {
                "success": True,
                "verified": True,
                "message": f"{app_name} is open and verified in the foreground.",
                "steps": 0,
            }

    return {
        "success": False,
        "verified": False,
        "message": (
            f"I launched {app_name}, but after waiting for the app to become "
            f"foreground, verification still shows {foreground or 'another app'}."
        ),
        "steps": 0,
    }


def _run_simple_open_path_goal(targets):
    """Execute a generic multi-step open path with verified checkpoints."""
    navigator = OpenPathNavigator()
    result = navigator.navigate("open " + " and open ".join(targets))
    return {
        "success": result.success,
        "verified": result.verified,
        "message": result.message,
        "steps": len(result.completed_targets),
        "targets": result.targets,
        "completed_targets": result.completed_targets,
        "failed_target": result.failed_target,
        "checkpoints": result.checkpoints,
    }


def _compact_history(messages):
    """Keep only recent action/observation pairs; current state is ground truth."""
    if len(messages) <= 2 + (MAX_HISTORY_PAIRS * 2):
        return messages
    recent = messages[-(MAX_HISTORY_PAIRS * 2):]
    return messages[:2] + recent


def run_agent(goal):
    """Run Nova's adaptive goal/action/observation loop for one goal."""
    goal = str(goal or "").strip()
    if not goal:
        return {"success": False, "message": "Goal cannot be empty."}

    simple_open_path = _simple_open_path_goal(goal)
    if simple_open_path:
        return _run_simple_open_path_goal(simple_open_path)

    simple_open_app = _simple_open_goal(goal)
    if simple_open_app:
        return _run_simple_open_goal(simple_open_app)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Accomplish this goal on the Android phone:\n" + goal},
    ]

    action_seen = False
    observed_after_action = False

    for step in range(1, MAX_STEPS + 1):
        messages = _compact_history(messages)
        message = call_ai(messages, build_agent_tool_definitions())
        messages.append(message)
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            answer = (message.get("content") or "").strip()
            if action_seen and not observed_after_action:
                messages.append({
                    "role": "system",
                    "content": (
                        "A state-changing action occurred but the resulting state "
                        "has not been observed. Call observe_android before claiming success."
                    ),
                })
                continue
            return {"success": True, "message": answer, "steps": step}

        tool_call = tool_calls[0]
        function = tool_call.get("function") or {}
        function_name = function.get("name", "")
        raw_arguments = function.get("arguments") or "{}"

        result = None
        arguments = {}
        try:
            arguments = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be a JSON object.")
        except (json.JSONDecodeError, ValueError) as exc:
            result = {"success": False, "verified": False, "message": f"Invalid tool arguments: {exc}"}

        if result is None:
            if function_name not in AGENT_TOOLS:
                result = {"success": False, "verified": False, "message": "Tool is not available to the adaptive agent."}
            else:
                print(f"🧠 Step {step}: {function_name}({arguments})")
                execution = execute_tool(function_name, function_name, **arguments)
                result = _unwrap_tool_result(execution)
                print("⚙️", result)

                if (
                    function_name not in {"observe_android", "find_android_app"}
                    and isinstance(result, dict)
                    and result.get("success")
                ):
                    fresh_observation = _observe_directly()
                    if isinstance(fresh_observation, dict):
                        print(
                            "👀 Auto-observe:",
                            _planner_tool_result(fresh_observation, "observe_android"),
                        )
                        observation_data = _planner_tool_result(fresh_observation, "observe_android")
                        result["post_action_observation"] = observation_data
                        observed_after_action = bool(fresh_observation.get("success"))
                    else:
                        observed_after_action = False
                elif function_name != "observe_android":
                    observed_after_action = False

        if function_name == "observe_android":
            if action_seen:
                observed_after_action = bool(result.get("success"))
        elif function_name == "find_android_app":
            pass
        else:
            action_seen = True
            if not (isinstance(result, dict) and result.get("post_action_observation")):
                observed_after_action = False

        messages.append(_tool_result_message(tool_call, result, function_name))

    return {
        "success": False,
        "verified": False,
        "message": "Nova reached its maximum planning steps before completing the goal.",
        "steps": MAX_STEPS,
    }


def main():
    import sys
    goal = " ".join(sys.argv[1:]).strip()
    result = run_agent(goal)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
