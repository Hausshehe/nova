"""Multi-provider AI router for Nova's adaptive planner."""

import copy
import os
import re
import time

import requests

PROVIDERS = {
    "groq": {"key": "GROQ_API_KEY", "url": "https://api.groq.com/openai/v1/chat/completions", "model_env": "GROQ_MODEL", "default_model": "openai/gpt-oss-120b"},
    "gemini": {"key": "GEMINI_API_KEY", "keys_env": "GEMINI_API_KEYS", "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "model_env": "GEMINI_MODEL", "default_model": "gemini-3.6-flash"},
    "cloudflare": {"key": "CLOUDFLARE_API_TOKEN", "url": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions", "model_env": "CLOUDFLARE_MODEL", "default_model": "@cf/nvidia/nemotron-3-120b-a12b", "account_env": "CLOUDFLARE_ACCOUNT_ID"},
    "mistral": {"key": "MISTRAL_API_KEY", "url": "https://api.mistral.ai/v1/chat/completions", "model_env": "MISTRAL_MODEL", "default_model": "mistral-small-latest"},
    "openrouter": {"key": "OPENROUTER_API_KEY", "url": "https://openrouter.ai/api/v1/chat/completions", "model_env": "OPENROUTER_MODEL", "default_model": "openrouter/free"},
}

# Gemini is intentionally last in the default chain for now. Its direct
# OpenAI-compatible Gemini 3 tool-calling endpoint can reject multi-turn
# histories when thought signatures are not round-tripped perfectly. When
# Gemini access is healthy, AI_PROVIDER_ORDER can promote it without code edits.
DEFAULT_ORDER = ["groq", "mistral", "openrouter", "cloudflare", "gemini"]
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_PROVIDER_COOLDOWN_UNTIL = {}
_GEMINI_KEY_COOLDOWN_UNTIL = {}
MAX_PROVIDER_COOLDOWN_SECONDS = 15 * 60
REQUEST_TIMEOUT_SECONDS = 12


def _provider_order():
    configured = os.environ.get("AI_PROVIDER_ORDER", "").strip()
    if not configured:
        return DEFAULT_ORDER
    requested = [name.strip().lower() for name in configured.split(",") if name.strip()]
    return [name for name in requested if name in PROVIDERS]


def _parse_duration(value):
    if not value:
        return None
    text = str(value).strip().lower()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    matches = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(ms|s|m|h)", text)
    if not matches:
        return None
    multipliers = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    return sum(float(number) * multipliers[unit] for number, unit in matches)


def _provider_retry_delay(response, status_code):
    headers = getattr(response, "headers", {}) or {}
    for header in ("retry-after", "Retry-After", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests", "x-ratelimit-reset"):
        delay = _parse_duration(headers.get(header))
        if delay is not None:
            return min(max(delay, 0.5) + 0.25, MAX_PROVIDER_COOLDOWN_SECONDS)
    try:
        text = str(response.json())
    except (ValueError, TypeError):
        text = getattr(response, "text", "") or ""
    match = re.search(r"(?:retry|try again|reset)[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)\s*(ms|seconds?|secs?|s|minutes?|mins?|m)", text, re.IGNORECASE)
    if match:
        unit = match.group(2).lower()
        unit = {"milliseconds": "ms", "seconds": "s", "second": "s", "secs": "s", "minutes": "m", "minute": "m", "mins": "m"}.get(unit, unit)
        delay = _parse_duration(match.group(1) + unit)
        if delay is not None:
            return min(max(delay, 0.5) + 0.25, MAX_PROVIDER_COOLDOWN_SECONDS)
    if status_code in {500, 502, 503, 504}:
        return 8.0
    if status_code in {408, 409, 425}:
        return 3.0
    return 30.0


def _mark_cooldown(provider, delay):
    _PROVIDER_COOLDOWN_UNTIL[provider] = time.monotonic() + max(0.5, delay)


def _is_cooled_down(provider):
    until = _PROVIDER_COOLDOWN_UNTIL.get(provider, 0.0)
    if until <= time.monotonic():
        _PROVIDER_COOLDOWN_UNTIL.pop(provider, None)
        return False
    return True


def _gemini_keys():
    raw_pool = os.environ.get("GEMINI_API_KEYS", "")
    keys = [item.strip() for item in raw_pool.split(",") if item.strip()]
    single = os.environ.get("GEMINI_API_KEY", "").strip()
    if single and single not in keys:
        keys.append(single)
    return keys


def _provider_has_key(provider):
    return bool(_gemini_keys()) if provider == "gemini" else bool(os.environ.get(PROVIDERS[provider]["key"]))


def _key_cooled_down(key):
    until = _GEMINI_KEY_COOLDOWN_UNTIL.get(key, 0.0)
    if until <= time.monotonic():
        _GEMINI_KEY_COOLDOWN_UNTIL.pop(key, None)
        return False
    return True


def _mark_key_cooldown(key, delay):
    _GEMINI_KEY_COOLDOWN_UNTIL[key] = time.monotonic() + max(0.5, delay)


def _headers(provider, api_key):
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/Hausshehe/nova"
        headers["X-Title"] = "Nova Adaptive Android Agent"
    return headers


def _provider_url(provider):
    config = PROVIDERS[provider]
    url = config["url"]
    account_env = config.get("account_env")
    if account_env:
        account_id = os.environ.get(account_env)
        if not account_id:
            return None
        url = url.format(account_id=account_id)
    return url


def _max_output_tokens():
    try:
        value = int(os.environ.get("NOVA_MAX_OUTPUT_TOKENS", "1600").strip())
    except ValueError:
        value = 1600
    return max(400, min(value, 8192))


def _copy_message(message):
    return {key: copy.deepcopy(value) for key, value in message.items()}


def _sanitize_messages(messages, provider):
    """Normalize history so every provider receives a valid tool-call sequence.

    This is deliberately generic: no app, screen, label, or navigation path is
    encoded here. Orphaned tool results are dropped when history compaction has
    removed their matching assistant tool call. This prevents strict providers
    such as Mistral from rejecting an otherwise valid adaptive session.
    """
    sanitized = []
    pending_tool_ids = set()
    tool_names = {}

    for original in messages:
        if not isinstance(original, dict):
            continue
        role = original.get("role")

        if role == "tool":
            call_id = original.get("tool_call_id")
            if not call_id or call_id not in pending_tool_ids:
                continue
            message = _copy_message(original)
            if provider == "gemini" and not message.get("name"):
                message["name"] = tool_names.get(call_id, "generic_tool")
            sanitized.append(message)
            pending_tool_ids.discard(call_id)
            continue

        if role == "assistant":
            # A new assistant turn means any old tool results that were not
            # present in this compact history can no longer be validly replayed.
            if pending_tool_ids:
                pending_tool_ids.clear()
            message = _copy_message(original)
            calls = message.get("tool_calls") or []
            if isinstance(calls, list):
                clean_calls = []
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") or {}
                    name = function.get("name")
                    call_id = call.get("id")
                    if not name or not call_id:
                        continue
                    clean_call = _copy_message(call)
                    clean_call["function"] = {
                        "name": name,
                        "arguments": function.get("arguments") or "{}",
                    }
                    if provider == "gemini" and "extra_content" in call:
                        clean_call["extra_content"] = copy.deepcopy(call["extra_content"])
                    clean_calls.append(clean_call)
                    pending_tool_ids.add(call_id)
                    tool_names[call_id] = name
                message["tool_calls"] = clean_calls
            sanitized.append(message)
            continue

        if role in {"system", "user"}:
            # A user/system turn cannot legally consume a pending tool result.
            pending_tool_ids.clear()
            sanitized.append(_copy_message(original))
            continue

        if original.get("content") is not None:
            pending_tool_ids.clear()
            sanitized.append({"role": "user", "content": copy.deepcopy(original["content"])})

    # Gemini 3 direct OpenAI compatibility supports one sequential tool call in
    # our planner. Keep the exact returned thought signature when present.
    if provider == "gemini":
        for message in sanitized:
            calls = message.get("tool_calls")
            if isinstance(calls, list) and len(calls) > 1:
                message["tool_calls"] = calls[:1]
    return sanitized


def _cross_provider_messages(messages):
    """Build provider-neutral history without replaying provider-specific tools."""
    portable = []
    for original in messages:
        if not isinstance(original, dict):
            continue
        role = original.get("role")
        content = original.get("content")
        if role in {"system", "user"}:
            if content is not None:
                portable.append({"role": role, "content": copy.deepcopy(content)})
            continue
        if role == "assistant":
            calls = original.get("tool_calls") or []
            text = content or ""
            if calls:
                selections = []
                for call in calls:
                    function = call.get("function") or {}
                    name = function.get("name") or "unknown_tool"
                    arguments = function.get("arguments") or "{}"
                    selections.append(f"Planner selected generic tool '{name}' with arguments {arguments}.")
                text = (text + "\n" if text else "") + "\n".join(selections)
            if text:
                # Avoid consecutive assistant messages when a model supplied
                # text plus tool calls in one turn.
                if portable and portable[-1].get("role") == "assistant":
                    portable[-1]["content"] += "\n" + text
                else:
                    portable.append({"role": "assistant", "content": text})
            continue
        if role == "tool":
            tool_name = original.get("name") or "generic_tool"
            result = content if content is not None else ""
            portable.append({
                "role": "user",
                "content": f"Result from previous generic tool '{tool_name}': {result}",
            })
            continue
    return portable


def _validate_message(message):
    if not isinstance(message, dict):
        return None, "Provider returned a non-object message"
    calls = message.get("tool_calls")
    if calls is None:
        return message, None
    if not isinstance(calls, list):
        return None, "Provider returned invalid tool_calls"
    for index, call in enumerate(calls):
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict) or not function.get("name"):
            return None, f"Provider returned a tool call without a function name at index {index}"
        if not call.get("id"):
            return None, f"Provider returned a tool call without an id at index {index}"
    return message, None


def _request(provider, messages, tools):
    config = PROVIDERS[provider]
    url = _provider_url(provider)
    if not url:
        return None, f"{config.get('account_env')} is not configured"
    model = os.environ.get(config["model_env"], config["default_model"])
    payload = {
        "model": model,
        "messages": _sanitize_messages(messages, provider),
        "temperature": 0.2,
        "max_tokens": _max_output_tokens(),
        "tools": tools,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
    }
    if provider == "gemini":
        payload["reasoning_effort"] = "low"

    keys = _gemini_keys() if provider == "gemini" else [os.environ.get(config["key"], "").strip()]
    keys = [key for key in keys if key]
    if not keys:
        return None, f"{config['key']} is not configured"

    failures = []
    for index, api_key in enumerate(keys, start=1):
        if provider == "gemini" and _key_cooled_down(api_key):
            continue
        try:
            response = requests.post(
                url,
                headers=_headers(provider, api_key),
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            failures.append(f"{provider} request failed: {exc}")
            continue

        if response.status_code == 200:
            try:
                data = response.json()
                message = data["choices"][0]["message"]
                valid_message, validation_error = _validate_message(message)
                if valid_message is not None:
                    return valid_message, None
                failures.append(validation_error)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                failures.append(f"{provider} returned an invalid response: {exc}")
            continue

        error = f"HTTP {response.status_code}: {response.text[:500]}"
        if provider == "gemini" and response.status_code in {401, 403}:
            _mark_key_cooldown(api_key, 15 * 60)
            failures.append(f"Gemini key {index} denied for ~900s: {error}")
            continue

        if response.status_code in RETRYABLE_STATUS:
            delay = _provider_retry_delay(response, response.status_code)
            if provider == "gemini":
                _mark_key_cooldown(api_key, delay)
                failures.append(f"Gemini key {index} limited for ~{delay:.1f}s: {error}")
                continue
            _mark_cooldown(provider, delay)
            return None, f"{error} (cooldown ~{delay:.1f}s)"

        failures.append(error)

    return None, " | ".join(failures) if failures else f"{provider} request failed"


def call_ai(messages, tools):
    """Return the first successful planner response from available providers."""
    configured = [provider for provider in _provider_order() if _provider_has_key(provider)]
    if not configured:
        raise RuntimeError("No AI provider API keys are configured.")

    failures = []
    skipped = []
    first_attempted_provider = None
    for provider in configured:
        if _is_cooled_down(provider):
            skipped.append(provider)
            continue
        if first_attempted_provider is None:
            first_attempted_provider = provider
        print(f"🤖 Planner provider: {provider}")
        provider_messages = messages
        if provider != first_attempted_provider:
            provider_messages = _cross_provider_messages(messages)
            print(f"🔄 Rebuilding portable planner history for provider switch: {first_attempted_provider} → {provider}")
        message, error = _request(provider, provider_messages, tools)
        if message is not None:
            return message
        failures.append(f"{provider}: {error}")
        print(f"⚠️ {provider} unavailable; failing over: {error}")

    if skipped:
        print("⏭️ Temporarily skipped providers: " + ", ".join(skipped))
    detail = " | ".join(failures) if failures else "All configured providers are temporarily cooling down."
    raise RuntimeError("All available AI providers failed or are cooling down. " + detail)


def provider_status():
    now = time.monotonic()
    status = {}
    for name, config in PROVIDERS.items():
        if name == "gemini":
            keys = _gemini_keys()
            status[name] = {
                "configured": bool(keys),
                "keys": len(keys),
                "model": os.environ.get(config["model_env"], config["default_model"]),
                "cooldown_seconds": max(0.0, _PROVIDER_COOLDOWN_UNTIL.get(name, 0.0) - now),
                "key_cooldowns": {
                    str(index + 1): max(0.0, _GEMINI_KEY_COOLDOWN_UNTIL.get(key, 0.0) - now)
                    for index, key in enumerate(keys)
                },
            }
        else:
            status[name] = {
                "configured": bool(os.environ.get(config["key"])),
                "model": os.environ.get(config["model_env"], config["default_model"]),
                "cooldown_seconds": max(0.0, _PROVIDER_COOLDOWN_UNTIL.get(name, 0.0) - now),
            }
    return status
