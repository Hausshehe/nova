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

DEFAULT_ORDER = ["groq", "gemini", "cloudflare", "mistral", "openrouter"]
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_PROVIDER_COOLDOWN_UNTIL = {}
_GEMINI_KEY_COOLDOWN_UNTIL = {}
MAX_PROVIDER_COOLDOWN_SECONDS = 15 * 60


def _provider_order():
    configured = os.environ.get("AI_PROVIDER_ORDER", "").strip()
    if not configured:
        return DEFAULT_ORDER
    requested = [name.strip().lower() for name in configured.split(",") if name.strip()]
    return [name for name in requested if name in PROVIDERS]


def _parse_duration(value):
    """Parse common provider durations such as '12.5s' or '1m30s'."""
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
    """Read retry/reset hints without sleeping; Nova fails over immediately."""
    headers = getattr(response, "headers", {}) or {}
    for header in ("retry-after", "Retry-After", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests", "x-ratelimit-reset"):
        delay = _parse_duration(headers.get(header))
        if delay is not None:
            return min(max(delay, 0.5) + 0.25, MAX_PROVIDER_COOLDOWN_SECONDS)

    try:
        body = response.json()
        text = str(body)
    except (ValueError, TypeError):
        text = getattr(response, "text", "") or ""
    match = re.search(r"(?:retry|try again|reset)[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)\s*(ms|seconds?|secs?|s|minutes?|mins?|m)", text, re.IGNORECASE)
    if match:
        unit = match.group(2).lower()
        normalized_unit = {"milliseconds": "ms", "seconds": "s", "second": "s", "secs": "s", "minutes": "m", "minute": "m", "mins": "m"}.get(unit, unit)
        delay = _parse_duration(match.group(1) + normalized_unit)
        if delay is not None:
            return min(max(delay, 0.5) + 0.25, MAX_PROVIDER_COOLDOWN_SECONDS)

    if status_code in {500, 502, 503, 504}:
        return 8.0
    if status_code in {408, 409, 425}:
        return 3.0
    return 30.0


def _mark_cooldown(provider, status_code, delay=None):
    if delay is None:
        delay = _cooldown_seconds(status_code)
    _PROVIDER_COOLDOWN_UNTIL[provider] = time.monotonic() + delay


def _cooldown_seconds(status_code):
    if status_code == 429:
        return 30.0
    if status_code in {500, 502, 503, 504}:
        return 8.0
    return 3.0


def _is_cooled_down(provider):
    until = _PROVIDER_COOLDOWN_UNTIL.get(provider, 0.0)
    if until <= time.monotonic():
        _PROVIDER_COOLDOWN_UNTIL.pop(provider, None)
        return False
    return True


def _gemini_keys():
    """Return legitimately controlled Gemini keys in configured order."""
    raw_pool = os.environ.get("GEMINI_API_KEYS", "")
    keys = [item.strip() for item in raw_pool.split(",") if item.strip()]
    single = os.environ.get("GEMINI_API_KEY", "").strip()
    if single and single not in keys:
        keys.append(single)
    return keys


def _provider_has_key(provider):
    if provider == "gemini":
        return bool(_gemini_keys())
    return bool(os.environ.get(PROVIDERS[provider]["key"]))


def _key_cooled_down(key):
    until = _GEMINI_KEY_COOLDOWN_UNTIL.get(key, 0.0)
    if until <= time.monotonic():
        _GEMINI_KEY_COOLDOWN_UNTIL.pop(key, None)
        return False
    return True


def _mark_key_cooldown(key, status_code, delay=None):
    if delay is None:
        delay = _cooldown_seconds(status_code)
    _GEMINI_KEY_COOLDOWN_UNTIL[key] = time.monotonic() + delay


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
    raw = os.environ.get("NOVA_MAX_OUTPUT_TOKENS", "1600").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 1600
    return max(400, min(value, 8192))


def _sanitize_messages(messages, provider):
    """Return provider-safe copies of the OpenAI-compatible conversation."""
    sanitized = []
    for original in messages:
        if not isinstance(original, dict):
            continue
        message = {key: copy.deepcopy(value) for key, value in original.items() if key in {"role", "content", "tool_calls", "tool_call_id", "name"}}
        if provider == "gemini":
            for key in ("extra_content", "reasoning_content", "reasoning_details"):
                if key in original:
                    message[key] = copy.deepcopy(original[key])
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            clean_calls = []
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                clean_call = copy.deepcopy(call)
                function = clean_call.get("function")
                if isinstance(function, dict):
                    clean_call["function"] = {
                        key: copy.deepcopy(value)
                        for key, value in function.items()
                        if key in {"name", "arguments"}
                    }
                clean_calls.append(clean_call)
            if provider == "gemini" and len(clean_calls) > 1:
                clean_calls = clean_calls[:1]
            message["tool_calls"] = clean_calls
        sanitized.append(message)
    return sanitized


def _cross_provider_messages(messages):
    """Convert provider-specific tool history into portable planner history.

    A provider's assistant tool calls can contain provider-specific metadata.
    Gemini 3, for example, requires thought signatures to be returned exactly
    on subsequent turns. That metadata cannot be reconstructed for a tool call
    produced by another provider, so switching providers must use a neutral
    textual representation instead of replaying foreign tool-call messages.
    """
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
            if content:
                portable.append({"role": "assistant", "content": copy.deepcopy(content)})
            calls = original.get("tool_calls") or []
            for call in calls:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") or {}
                name = function.get("name") or "unknown_tool"
                arguments = function.get("arguments") or "{}"
                portable.append({
                    "role": "assistant",
                    "content": f"Planner selected generic tool '{name}' with arguments {arguments}."
                })
            continue

        if role == "tool":
            tool_name = original.get("name") or "generic_tool"
            if content is None:
                content = ""
            portable.append({
                "role": "user",
                "content": f"Result from previous generic tool '{tool_name}': {content}"
            })
            continue

        if content is not None:
            portable.append({"role": "user", "content": copy.deepcopy(content)})

    return portable


def _validate_message(message):
    """Reject malformed tool calls before they enter Nova's shared history."""
    if not isinstance(message, dict):
        return None, "Provider returned a non-object message"
    tool_calls = message.get("tool_calls")
    if tool_calls is None:
        return message, None
    if not isinstance(tool_calls, list):
        return None, "Provider returned invalid tool_calls"
    for index, call in enumerate(tool_calls):
        if not isinstance(call, dict):
            return None, f"Provider returned invalid tool call at index {index}"
        function = call.get("function")
        if not isinstance(function, dict) or not function.get("name"):
            return None, f"Provider returned a tool call without a function name at index {index}"
        if not call.get("id"):
            return None, f"Provider returned a tool call without an id at index {index}"
    return message, None


def _request(provider, messages, tools):
    config = PROVIDERS[provider]
    url = _provider_url(provider)
    if not url:
        account_env = config.get("account_env")
        return None, f"{account_env} is not configured"
    model = os.environ.get(config["model_env"], config["default_model"])
    payload = {"model": model, "messages": _sanitize_messages(messages, provider), "temperature": 0.2, "max_tokens": _max_output_tokens(), "tools": tools, "tool_choice": "auto", "parallel_tool_calls": False}
    keys = _gemini_keys() if provider == "gemini" else [os.environ.get(config["key"], "").strip()]
    keys = [key for key in keys if key]
    if not keys:
        return None, f"{config['key']} is not configured"
    failures = []
    for api_key in keys:
        if provider == "gemini" and _key_cooled_down(api_key):
            continue
        for attempt in range(2):
            try:
                response = requests.post(url, headers=_headers(provider, api_key), json=payload, timeout=30)
            except requests.RequestException as exc:
                if attempt == 0:
                    time.sleep(0.8)
                    continue
                failures.append(str(exc))
                break
            if response.status_code == 200:
                try:
                    data = response.json()
                    message = data["choices"][0]["message"]
                    valid_message, validation_error = _validate_message(message)
                    if valid_message is None:
                        failures.append(validation_error)
                        break
                    return valid_message, None
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    return None, f"{provider} returned an invalid response: {exc}"
            error = f"HTTP {response.status_code}: {response.text[:500]}"
            if response.status_code in RETRYABLE_STATUS:
                delay = _provider_retry_delay(response, response.status_code)
                if provider == "gemini":
                    _mark_key_cooldown(api_key, response.status_code, delay)
                    failures.append(f"Gemini key limited for ~{delay:.1f}s: {error}")
                    break
                _mark_cooldown(provider, response.status_code, delay)
                return None, f"{error} (cooldown ~{delay:.1f}s)"
            return None, error
    if provider == "gemini" and failures:
        return None, " | ".join(failures)
    if failures:
        return None, " | ".join(failures)
    return None, f"{provider} request failed"


def call_ai(messages, tools):
    """Return the first successful planner response from available providers."""
    configured = [provider for provider in _provider_order() if _provider_has_key(provider)]
    if not configured:
        raise RuntimeError("No AI provider API keys are configured. Set at least one of GROQ_API_KEY, GEMINI_API_KEY/GEMINI_API_KEYS, CLOUDFLARE_API_TOKEN, MISTRAL_API_KEY, or OPENROUTER_API_KEY.")
    failures = []
    skipped = []
    last_successful_provider = None
    for provider in configured:
        if _is_cooled_down(provider):
            skipped.append(provider)
            continue
        print(f"🤖 Planner provider: {provider}")
        provider_messages = messages
        if last_successful_provider and provider != last_successful_provider:
            provider_messages = _cross_provider_messages(messages)
            print(f"🔄 Rebuilding portable planner history for provider switch: {last_successful_provider} → {provider}")
        message, error = _request(provider, provider_messages, tools)
        if message is not None:
            last_successful_provider = provider
            return message
        failures.append(f"{provider}: {error}")
        print(f"⚠️ {provider} unavailable; failing over: {error}")
    if skipped:
        print("⏭️ Temporarily skipped providers: " + ", ".join(skipped))
    detail = " | ".join(failures) if failures else "All configured providers are temporarily cooling down."
    raise RuntimeError("All available AI providers failed or are cooling down. " + detail)


def provider_status():
    """Return a small diagnostic view of configured providers and cooldowns."""
    now = time.monotonic()
    status = {}
    for name, config in PROVIDERS.items():
        if name == "gemini":
            keys = _gemini_keys()
            status[name] = {"configured": bool(keys), "keys": len(keys), "model": os.environ.get(config["model_env"], config["default_model"]), "cooldown_seconds": max(0.0, _PROVIDER_COOLDOWN_UNTIL.get(name, 0.0) - now), "key_cooldowns": {str(index + 1): max(0.0, _GEMINI_KEY_COOLDOWN_UNTIL.get(key, 0.0) - now) for index, key in enumerate(keys)}}
        else:
            status[name] = {"configured": bool(os.environ.get(config["key"])), "model": os.environ.get(config["model_env"], config["default_model"]), "cooldown_seconds": max(0.0, _PROVIDER_COOLDOWN_UNTIL.get(name, 0.0) - now)}
    return status
