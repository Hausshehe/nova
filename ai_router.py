"""Multi-provider AI router for Nova's adaptive planner."""

import copy
import os
import time

import requests


PROVIDERS = {
    "groq": {
        "key": "GROQ_API_KEY",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model_env": "GROQ_MODEL",
        "default_model": "openai/gpt-oss-120b",
    },
    "gemini": {
        "key": "GEMINI_API_KEY",
        "keys_env": "GEMINI_API_KEYS",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-3.6-flash",
    },
    "cloudflare": {
        "key": "CLOUDFLARE_API_TOKEN",
        "url": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions",
        "model_env": "CLOUDFLARE_MODEL",
        "default_model": "@cf/nvidia/nemotron-3-120b-a12b",
        "account_env": "CLOUDFLARE_ACCOUNT_ID",
    },
    "mistral": {
        "key": "MISTRAL_API_KEY",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model_env": "MISTRAL_MODEL",
        "default_model": "mistral-small-latest",
    },
    "openrouter": {
        "key": "OPENROUTER_API_KEY",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model_env": "OPENROUTER_MODEL",
        "default_model": "openrouter/free",
    },
}

# Groq remains Nova's fast primary planner. Gemini is the first fallback.
DEFAULT_ORDER = ["groq", "gemini", "cloudflare", "mistral", "openrouter"]
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_PROVIDER_COOLDOWN_UNTIL = {}
_GEMINI_KEY_COOLDOWN_UNTIL = {}


def _provider_order():
    configured = os.environ.get("AI_PROVIDER_ORDER", "").strip()
    if not configured:
        return DEFAULT_ORDER

    requested = [name.strip().lower() for name in configured.split(",") if name.strip()]
    return [name for name in requested if name in PROVIDERS]


def _cooldown_seconds(status_code):
    if status_code == 429:
        return 30.0
    if status_code in {500, 502, 503, 504}:
        return 8.0
    return 3.0


def _mark_cooldown(provider, status_code):
    _PROVIDER_COOLDOWN_UNTIL[provider] = time.monotonic() + _cooldown_seconds(status_code)


def _is_cooled_down(provider):
    until = _PROVIDER_COOLDOWN_UNTIL.get(provider, 0.0)
    if until <= time.monotonic():
        _PROVIDER_COOLDOWN_UNTIL.pop(provider, None)
        return False
    return True


def _gemini_keys():
    """Return configured Gemini keys in rotation order.

    GEMINI_API_KEYS may contain comma-separated keys. GEMINI_API_KEY remains
    supported for backward compatibility. Only use keys/projects legitimately
    controlled by the user; this is provider failover, not quota evasion.
    """
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


def _mark_key_cooldown(key, status_code):
    _GEMINI_KEY_COOLDOWN_UNTIL[key] = time.monotonic() + _cooldown_seconds(status_code)


def _headers(provider, api_key):
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
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
    """Return Nova's adaptive output budget without hard-coding 800 tokens."""
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

        message = {
            key: copy.deepcopy(value)
            for key, value in original.items()
            if key in {"role", "content", "tool_calls", "tool_call_id", "name"}
        }

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

                clean_call = {
                    key: copy.deepcopy(value)
                    for key, value in call.items()
                    if key in {"id", "type", "function"}
                }

                if provider == "gemini" and "extra_content" in call:
                    clean_call["extra_content"] = copy.deepcopy(call["extra_content"])

                function = clean_call.get("function")
                if isinstance(function, dict):
                    clean_call["function"] = {
                        key: copy.deepcopy(value)
                        for key, value in function.items()
                        if key in {"name", "arguments"}
                    }

                clean_calls.append(clean_call)
            message["tool_calls"] = clean_calls

        sanitized.append(message)

    return sanitized


def _request(provider, messages, tools):
    config = PROVIDERS[provider]
    url = _provider_url(provider)
    if not url:
        account_env = config.get("account_env")
        return None, f"{account_env} is not configured"

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
                response = requests.post(
                    url,
                    headers=_headers(provider, api_key),
                    json=payload,
                    timeout=30,
                )
            except requests.RequestException as exc:
                if attempt == 0:
                    time.sleep(0.8)
                    continue
                failures.append(str(exc))
                break

            if response.status_code == 200:
                try:
                    data = response.json()
                    return data["choices"][0]["message"], None
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    return None, f"{provider} returned an invalid response: {exc}"

            error = f"HTTP {response.status_code}: {response.text[:500]}"

            if response.status_code in RETRYABLE_STATUS:
                if provider == "gemini":
                    _mark_key_cooldown(api_key, response.status_code)
                    failures.append(f"Gemini key limited: {error}")
                    break
                _mark_cooldown(provider, response.status_code)
                return None, error

            return None, error

    if provider == "gemini" and failures:
        return None, " | ".join(failures)
    return None, f"{provider} request failed"


def call_ai(messages, tools):
    """Return the first successful planner response from available providers."""
    configured = [provider for provider in _provider_order() if _provider_has_key(provider)]

    if not configured:
        raise RuntimeError(
            "No AI provider API keys are configured. Set at least one of "
            "GROQ_API_KEY, GEMINI_API_KEY/GEMINI_API_KEYS, "
            "CLOUDFLARE_API_TOKEN, MISTRAL_API_KEY, or OPENROUTER_API_KEY."
        )

    failures = []
    skipped = []

    for provider in configured:
        if _is_cooled_down(provider):
            skipped.append(provider)
            continue

        print(f"🤖 Planner provider: {provider}")
        message, error = _request(provider, messages, tools)
        if message is not None:
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
            configured = bool(_gemini_keys())
            model = os.environ.get(config["model_env"], config["default_model"])
            status[name] = {
                "configured": configured,
                "keys": len(_gemini_keys()),
                "model": model,
                "cooldown_seconds": max(0.0, _PROVIDER_COOLDOWN_UNTIL.get(name, 0.0) - now),
            }
        else:
            status[name] = {
                "configured": bool(os.environ.get(config["key"])),
                "model": os.environ.get(config["model_env"], config["default_model"]),
                "cooldown_seconds": max(0.0, _PROVIDER_COOLDOWN_UNTIL.get(name, 0.0) - now),
            }
    return status
