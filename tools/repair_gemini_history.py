"""Repair Gemini tool-history compatibility in an existing Nova checkout.

This maintenance script is intentionally separate from the runtime tool registry.
Run it once from the Nova root after pulling it.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "ai_router.py"

text = ROUTER.read_text()

old = '''def _sanitize_messages(messages, provider):
    """Return provider-safe copies of the OpenAI-compatible conversation."""
    sanitized = []
    for original in messages:
'''

new = '''def _sanitize_messages(messages, provider):
    """Return provider-safe copies of the OpenAI-compatible conversation.

    Gemini's OpenAI-compatible endpoint still requires a tool-result message to
    carry the name of the function that produced it. Nova historically stored
    only tool_call_id, so after a normal planner turn Gemini could reject the
    next request with `function_response.name: Name cannot be empty`.
    """
    sanitized = []
    tool_names = {}

    for original in messages:
        if not isinstance(original, dict):
            continue

        # Build an id -> function-name map from the preceding assistant turn.
        for call in original.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function") or {}
            call_id = call.get("id")
            name = function.get("name")
            if call_id and name:
                tool_names[call_id] = name

        message = {key: copy.deepcopy(value) for key, value in original.items() if key in {"role", "content", "tool_calls", "tool_call_id", "name"}}

        # Gemini rejects tool results without a function name. Recover it from
        # the matching assistant tool call instead of inventing a tool name.
        if provider == "gemini" and message.get("role") == "tool":
            call_id = message.get("tool_call_id")
            if not message.get("name") and call_id in tool_names:
                message["name"] = tool_names[call_id]

        if provider == "gemini":
            for key in ("extra_content", "reasoning_content", "reasoning_details"):
                if key in original:
                    message[key] = copy.deepcopy(original[key])

        tool_calls = message.get("tool_calls")
'''

if old not in text:
    raise SystemExit("Could not locate _sanitize_messages().")

text = text.replace(old, new, 1)

# The existing implementation already preserves Gemini thought metadata at the
# tool-call level. Keep that behavior while making the function-name mapping
# explicit for future maintainers.
ROUTER.write_text(text)
print("Repaired Gemini tool-result history handling in ai_router.py")
print("Run: python -m py_compile ai_router.py")
