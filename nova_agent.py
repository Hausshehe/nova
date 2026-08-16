
    return result


def _tool_result_message(tool_call, result, function_name):
    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(
            _planner_tool_result(result, function_name),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def _simple_open_goal(goal):
    """Recognize only a standalone generic 'open/launch/start app' goal.

    Any additional instruction after the app name must stay on Nova's
    adaptive planner path. This prevents multi-step goals such as
    'open Settings and find Display settings' from being misclassified
    as a simple app launch.
    """
    normalized = re.sub(r"\s+", " ", str(goal or "").strip().lower())
    match = re.fullmatch(
        r"(?:open|launch|start)\s+(.+?)(?:\s+app)?",
        normalized,
    )
    if not match:
        return ""

    app_name = match.group(1).strip()
    if not app_name:
        return ""

    # A standalone app-open goal must not contain conjunctions or
    # follow-up/action phrases. Those belong to the adaptive planner.
    if re.search(
        r"\b(?:and|then|after|before|find|search|look|tap|click|type|enter|send|message|call|change|enable|disable|turn|set|go|navigate)\b",
        app_name,
    ):
        return ""

    return app_name


def _observe_directly():
    """Observe without spending another planner/Groq turn."""
    return _unwrap_tool_result(
        execute_tool("observe_android", "observe_android")
    )