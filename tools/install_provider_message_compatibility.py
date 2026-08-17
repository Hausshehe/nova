"""Install cross-provider message normalization for Nova's AI router.

The planner shares conversation history between providers. Providers can return
provider-specific assistant fields (for example Cloudflare annotations/reasoning)
and some OpenAI-compatible endpoints require a tool result name. Normalize the
history at the router boundary so failover providers see portable messages.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "ai_router.py"
AGENT = ROOT / "nova_agent.py"


def update_router():
    text = ROUTER.read_text()
    old = '''def _request(provider, messages, tools):\n    config = PROVIDERS[provider]\n'''
    new = '''def _sanitize_messages(messages):\n    """Convert provider-returned messages into portable OpenAI-style history.\n\n    Nova can fail over after a tool call. The previous provider may have added\n    fields such as annotations, reasoning, audio, or provider-specific metadata\n    that another provider rejects. Keep only the common conversation/tool fields.\n    """\n    sanitized = []\n    for message in messages:\n        if not isinstance(message, dict):\n            continue\n\n        role = message.get("role")\n        if role == "system" or role == "user":\n            item = {"role": role, "content": message.get("content") or ""}\n            sanitized.append(item)\n            continue\n\n        if role == "assistant":\n            item = {\n                "role": "assistant",\n                "content": message.get("content"),\n            }\n            tool_calls = message.get("tool_calls") or []\n            if tool_calls:\n                clean_calls = []\n                for call in tool_calls:\n                    if not isinstance(call, dict):\n                        continue\n                    function = call.get("function") or {}\n                    name = function.get("name") or ""\n                    if not name:\n                        continue\n                    clean_calls.append({\n                        "id": call.get("id") or f"call_{len(clean_calls)}",\n                        "type": "function",\n                        "function": {\n                            "name": name,\n                            "arguments": function.get("arguments") or "{}",\n                        },\n                    })\n                if clean_calls:\n                    item["tool_calls"] = clean_calls\n            sanitized.append(item)\n            continue\n\n        if role == "tool":\n            item = {\n                "role": "tool",\n                "tool_call_id": message.get("tool_call_id") or "",\n                "content": message.get("content") or "",\n            }\n            # Gemini's OpenAI-compatible endpoint requires the function name on\n            # function-response messages. Nova adds it when executing a tool.\n            if message.get("name"):\n                item["name"] = message["name"]\n            sanitized.append(item)\n            continue\n\n    return sanitized\n\n\ndef _request(provider, messages, tools):\n    config = PROVIDERS[provider]\n'''
    if old not in text:
        raise SystemExit("Router request block not found")
    text = text.replace(old, new, 1)
    old_payload = '''    payload = {\n        "model": model,\n        "messages": messages,\n'''
    new_payload = '''    messages = _sanitize_messages(messages)\n\n    payload = {\n        "model": model,\n        "messages": messages,\n'''
    if old_payload not in text:
        raise SystemExit("Router payload block not found")
    text = text.replace(old_payload, new_payload, 1)
    ROUTER.write_text(text)


def update_agent():
    text = AGENT.read_text()
    old = '''def _tool_result_message(tool_call, result, function_name):\n    return {\n        "role": "tool",\n        "tool_call_id": tool_call["id"],\n        "content": json.dumps(\n'''
    new = '''def _tool_result_message(tool_call, result, function_name):\n    return {\n        "role": "tool",\n        "tool_call_id": tool_call["id"],\n        "name": function_name,\n        "content": json.dumps(\n'''
    if old not in text:
        raise SystemExit("Agent tool result block not found")
    text = text.replace(old, new, 1)
    AGENT.write_text(text)


if __name__ == "__main__":
    update_router()
    update_agent()
    print("✅ Installed provider-neutral message normalization.")
    print("   Tool responses now carry their function name for Gemini compatibility.")
    print("   Provider-specific assistant metadata is stripped before failover.")
