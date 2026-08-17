from pathlib import Path
import re

TARGET = Path(__file__).resolve().parents[1] / "nova_agent.py"

HELPER = '''def _action_is_goal_endpoint(goal, function_name, arguments):
    """Return True when a successful action matches the terminal intent of the goal."""
    if function_name not in {"click_text", "click_node"}:
        return False
    if not isinstance(arguments, dict):
        return False

    target = arguments.get("text")
    if not target:
        selector = arguments.get("selector")
        if isinstance(selector, dict):
            target = selector.get("text") or selector.get("content_description")
    if not isinstance(target, str) or not target.strip():
        return False

    normalize = lambda value: re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    goal_text = normalize(str(goal or ""))
    target_text = normalize(target)
    if not goal_text or not target_text:
        return False

    # The terminal action is usually the final semantic phrase in a compound
    # request. Do not trigger for an earlier click that still has work after it.
    return goal_text.endswith(target_text)


'''

text = TARGET.read_text(encoding="utf-8")

if "def _action_is_goal_endpoint(" not in text:
    marker = "def _simple_open_goal(goal):\n"
    if marker not in text:
        raise SystemExit("Could not find _simple_open_goal marker")
    text = text.replace(marker, HELPER + marker, 1)

needle = '''        if function_name == "observe_android":
            if action_seen:
                observed_after_action = bool(result.get("success"))
        else:
            action_seen = True
            observed_after_action = False

        messages.append(_tool_result_message(tool_call, result, function_name))
'''

replacement = '''        if function_name == "observe_android":
            if action_seen:
                observed_after_action = bool(result.get("success"))
        else:
            action_seen = True
            observed_after_action = False

        # A verified click on the terminal action of a compound goal is enough
        # to complete the goal. This is generic and does not name any app or UI.
        if (
            isinstance(result, dict)
            and result.get("success")
            and result.get("verified")
            and _action_is_goal_endpoint(goal, function_name, arguments)
        ):
            target = arguments.get("text")
            if not target and isinstance(arguments.get("selector"), dict):
                selector = arguments["selector"]
                target = selector.get("text") or selector.get("content_description")
            return {
                "success": True,
                "verified": True,
                "message": f"Goal completed successfully by verified action: {target or function_name}.",
                "steps": step,
            }

        messages.append(_tool_result_message(tool_call, result, function_name))
'''

if needle not in text:
    raise SystemExit("Could not find run_agent action-result block")

text = text.replace(needle, replacement, 1)
TARGET.write_text(text, encoding="utf-8")
print("Installed generic terminal-action goal completion.")
