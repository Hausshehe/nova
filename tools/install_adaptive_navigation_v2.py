"""Install generic adaptive-navigation improvements into Nova's local planner.

This installer patches the user's current nova_agent.py instead of replacing it,
so local planner/router work is preserved. The change is provider-agnostic and
does not add app-specific navigation rules.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "nova_agent.py"


IMPORT_MARKER = "from tools.registry import discover_tools\n"
IMPORT_LINE = "from ai_router import call_ai\n"

HELPER_MARKER = "\ndef _compact_history(messages):\n"
HELPER = r'''

def _auto_observe_after_action(function_name, result):
    """Capture fresh Android state after every successful state-changing action.

    This is deliberately generic: the planner still decides what the next
    action should be. The runner simply gives it fresh ground-truth state
    without forcing it to spend an extra planner turn calling observe_android.
    """
    if function_name == "observe_android":
        return None
    if not isinstance(result, dict) or not result.get("success"):
        return None

    try:
        observation = _observe_directly()
    except Exception as exc:
        return {
            "success": False,
            "verified": False,
            "message": f"Automatic post-action observation failed: {exc}",
        }

    return _planner_tool_result(observation, "observe_android")
'''

OLD_APPEND = '        messages.append(_tool_result_message(tool_call, result, function_name))\n'
NEW_APPEND = r'''        messages.append(_tool_result_message(tool_call, result, function_name))

        # Give the next planner turn fresh ground-truth UI state immediately.
        # This prevents a scroll/click from being followed by stale reasoning
        # while keeping navigation fully model-driven and non-hard-coded.
        if function_name != "observe_android" and result.get("success"):
            fresh_state = _auto_observe_after_action(function_name, result)
            if fresh_state is not None:
                messages.append({
                    "role": "user",
                    "content": (
                        "Fresh Android UI state captured automatically after "
                        f"{function_name}:\n"
                        + __import__("json").dumps(
                            fresh_state,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                })
                observed_after_action = bool(fresh_state.get("success"))
'''

PROMPT_OLD = "- After any state-changing action, observe before choosing another action.\n"
PROMPT_NEW = "- After any state-changing action, use the fresh post-action observation supplied by the runner before choosing another action.\n"


def main():
    if not TARGET.exists():
        raise SystemExit(f"Missing {TARGET}")

    text = TARGET.read_text(encoding="utf-8")
    changed = False

    if IMPORT_LINE not in text:
        if IMPORT_MARKER not in text:
            raise SystemExit("Could not find Nova's tool import section.")
        text = text.replace(IMPORT_MARKER, IMPORT_MARKER + IMPORT_LINE, 1)
        changed = True

    if "def _auto_observe_after_action(" not in text:
        if HELPER_MARKER not in text:
            raise SystemExit("Could not find Nova's _compact_history section.")
        text = text.replace(HELPER_MARKER, HELPER + HELPER_MARKER, 1)
        changed = True

    if NEW_APPEND not in text:
        if OLD_APPEND not in text:
            raise SystemExit("Could not find Nova's tool-result append point.")
        text = text.replace(OLD_APPEND, NEW_APPEND, 1)
        changed = True

    if PROMPT_OLD in text and PROMPT_NEW not in text:
        text = text.replace(PROMPT_OLD, PROMPT_NEW, 1)
        changed = True

    TARGET.write_text(text, encoding="utf-8")

    if changed:
        print("✅ Installed generic post-action UI observation for Nova.")
        print("   Scrolls/clicks now feed fresh UI state to the next planner turn.")
        print("   No app-specific navigation rules were added.")
    else:
        print("ℹ️ Adaptive post-action observation is already installed.")


if __name__ == "__main__":
    main()
