"""Install robust multi-provider tool-history handling for Nova.

Fixes two classes of failures seen with Gemini 3 and cross-provider failover:
1. Gemini function responses require a non-empty function name.
2. A tool-call turn should stay on the provider that produced it when possible;
   provider-specific assistant metadata must not be replayed to another provider.

The agent remains generic and adaptive. No app-specific navigation is added.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "ai_router.py"
AGENT = ROOT / "nova_agent.py"


def update_agent():
    text = AGENT.read_text()
    old = '''def _tool_result_message(tool_call, result, function_name):\n    return {\n        "role": "tool",\n        "tool_call_id": tool_call["id"],\n        "content": json.dumps(\n'''
    new = '''def _tool_result_message(tool_call, result, function_name):\n    # Gemini's OpenAI-compatible endpoint needs the function name on the\n    # corresponding tool result. Other OpenAI-compatible providers also accept\n    # this field, so keeping it is provider-neutral.\n    return {\n        "role": "tool",\n        "tool_call_id": tool_call.get("id") or function_name,\n        "name": function_name,\n        "content": json.dumps(\n'''
    if old in text and new not in text:
        text = text.replace(old, new, 1)
    elif old not in text and '"name": function_name' not in text:
        raise SystemExit("Agent tool-result block not found")
    AGENT.write_text(text)


def update_router():
    text = ROUTER.read_text()

    marker = '_PROVIDER_COOLDOWN_UNTIL = {}\n'
    if '_ACTIVE_PROVIDER = None' not in text:
        if marker not in text:
            raise SystemExit("Router cooldown marker not found")
        text = text.replace(marker, marker + '_ACTIVE_PROVIDER = None\n', 1)

    helper_marker = 'def _request(provider, messages, tools):\n'
    if 'def _sanitize_messages_for_provider' not in text:
        helper = '''def _sanitize_messages_for_provider(provider, messages):\n    """Keep provider-specific history only when replaying to that provider."""\n    if provider == "gemini":\n        # Gemini 3 requires its extra_content.google.thought_signature to be\n        # replayed exactly on subsequent function-calling turns.\n        return messages\n\n    sanitized = []\n    for message in messages:\n        if not isinstance(message, dict):\n            continue\n        role = message.get("role")\n\n        if role in {"system", "user"}:\n            sanitized.append({\n                "role": role,\n                "content": message.get("content") or "",\n            })\n            continue\n\n        if role == "assistant":\n            item = {\n                "role": "assistant",\n                # Some providers reject null assistant content.\n                "content": message.get("content") or "[TOOL CALL]"\n                if message.get("tool_calls") else message.get("content") or "",\n            }\n            clean_calls = []\n            for call in message.get("tool_calls") or []:\n                if not isinstance(call, dict):\n                    continue\n                fn = call.get("function") or {}\n                name = fn.get("name") or ""\n                if not name:\n                    continue\n                clean_calls.append({\n                    "id": call.get("id") or name,\n                    "type": "function",\n                    "function": {\n                        "name": name,\n                        "arguments": fn.get("arguments") or "{}",\n                    },\n                })\n            if clean_calls:\n                item["tool_calls"] = clean_calls\n            sanitized.append(item)\n            continue\n\n        if role == "tool":\n            item = {\n                "role": "tool",\n                "tool_call_id": message.get("tool_call_id") or message.get("name") or "tool_call",\n                "name": message.get("name") or "tool",\n                "content": message.get("content") or "",\n            }\n            sanitized.append(item)\n            continue\n\n    return sanitized\n\n\n'''
        text = text.replace(helper_marker, helper + helper_marker, 1)

    old_payload = '''    model = os.environ.get(config["model_env"], config["default_model"])\n    payload = {\n        "model": model,\n        "messages": messages,\n'''
    new_payload = '''    model = os.environ.get(config["model_env"], config["default_model"])\n    messages = _sanitize_messages_for_provider(provider, messages)\n    payload = {\n        "model": model,\n        "messages": messages,\n'''
    if old_payload in text and new_payload not in text:
        text = text.replace(old_payload, new_payload, 1)

    # Replace call_ai with provider affinity: once a provider successfully emits
    # a tool call, keep using it on the next turn. If it fails, fail over once
    # and permanently move the session to the new provider for that turn.
    start = text.find('def call_ai(messages, tools):')
    end = text.find('\n\ndef provider_status():', start)
    if start == -1 or end == -1:
        raise SystemExit("call_ai block not found")

    new_call_ai = '''def call_ai(messages, tools):\n    """Return a planner response while preserving provider/session affinity."""\n    global _ACTIVE_PROVIDER\n\n    configured = [\n        provider\n        for provider in _provider_order()\n        if os.environ.get(PROVIDERS[provider]["key"])\n    ]\n    if not configured:\n        raise RuntimeError(\n            "No AI provider API keys are configured. Set at least one of "\n            "GEMINI_API_KEY, GROQ_API_KEY, CLOUDFLARE_API_TOKEN, "\n            "MISTRAL_API_KEY, or OPENROUTER_API_KEY."\n        )\n\n    ordered = []\n    if _ACTIVE_PROVIDER in configured:\n        ordered.append(_ACTIVE_PROVIDER)\n    ordered.extend(provider for provider in configured if provider not in ordered)\n\n    failures = []\n    skipped = []\n    for provider in ordered:\n        if _is_cooled_down(provider):\n            skipped.append(provider)\n            continue\n\n        print(f"🤖 Planner provider: {provider}")\n        message, error = _request(provider, messages, tools)\n        if message is not None:\n            _ACTIVE_PROVIDER = provider\n            return message\n\n        if _ACTIVE_PROVIDER == provider:\n            _ACTIVE_PROVIDER = None\n        failures.append(f"{provider}: {error}")\n        print(f"⚠️ {provider} unavailable; failing over: {error}")\n\n    if skipped:\n        print("⏭️ Temporarily skipped providers: " + ", ".join(skipped))\n\n    detail = " | ".join(failures) if failures else "All configured providers are temporarily cooling down."\n    raise RuntimeError("All available AI providers failed or are cooling down. " + detail)\n'''
    text = text[:start] + new_call_ai + text[end:]
    ROUTER.write_text(text)


if __name__ == "__main__":
    update_agent()
    update_router()
    print("✅ Installed provider affinity and portable tool-history handling.")
    print("   Gemini tool results now include the function name and tool-call ID.")
    print("   Gemini thought signatures are preserved for Gemini requests.")
    print("   Failover providers receive sanitized portable history.")
    print("   Nova stays on the successful provider between planner turns.")
