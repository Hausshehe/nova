"""Multi-provider AI router for Nova's adaptive planner.

Nova stays provider-agnostic: every provider receives the same generic tool
contract, while the router adapts conversation history to each provider's
wire-format requirements. This is especially important for Gemini 3 thought
signatures, which must be preserved exactly during multi-step tool calling.
"""

import copy
import os
import time

import requests


PROVIDERS = {
    "gemini": {
        "key": "GEMINI_API_KEY",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-3.6-flash",
    },
    "groq": {
        "key": "GROQ_API_KEY",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model_env": "GROQ_MODEL",
        "default_model": "openai/gpt-oss-120b",
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

DEFAULT_ORDER = ["gemini", "groq", "cloudflare", "mistral", "openrouter"]
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_PROVIDER_COOLDOWN_UNTIL = {}


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
    """Return provider-safe copies of the OpenAI-compatible conversation.

    Nova keeps one canonical history so the planner remains provider-agnostic.
    Provider APIs, however, do not accept every extension produced by another
    provider. Gemini 3 is special: its OpenAI-compatible API puts the required
    thought signature inside tool-call ``extra_content`` and requires that
    field to be replayed exactly during sequential function calling.

    For non-Gemini providers we deliberately strip provider-specific metadata
    such as ``extra_content`` and ``annotations``. This prevents Gemini-only
    fields from leaking into Groq/Cloudflare/Mistral/OpenRouter requests.
    """
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
            # Preserve Gemini's response metadata exactly where it was emitted.
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
                    # Google documents this field as the OpenAI-compatibility
                    # carrier for Gemini 3 thought_signature.
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

        # Gemini's OpenAI-compatible endpoint needs assistant messages with
        # tool calls replayed as assistant messages. Other providers should
        # receive the normal OpenAI-compatible shape only.
        sanitized.append(message)

    return sanitized


def _request(provider, messages, tools):
    config = PROVIDERS[provider]
    api_key = os.environ.get(config["key"])
    if not api_key:
        return None, f"{config['key']} is not configured"

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
            return None, str(exc)

        if response.status_code == 200:
            try:
                data = response.json()
                return data["choices"][0]["message"], None
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                return None, f"{provider} returned an invalid response: {exc}"

        error = f"HTTP {response.status_code}: {response.text[:500]}"

        if response.status_code in RETRYABLE_STATUS:
            _mark_cooldown(provider, response.status_code)
            return None, error

        return None, error

    return None, f"{provider} request failed"


def call_ai(messages, tools):
    """Return the first successful planner response from available providers."""
    configured = [
        provider
        for provider in _provider_order()
        if os.environ.get(PROVIDERS[provider]["key"])
    ]

    if not configured:
        raise RuntimeError(
            "No AI provider API keys are configured. Set at least one of "
            "GEMINI_API_KEY, GROQ_API_KEY, CLOUDFLARE_API_TOKEN, "
            "MISTRAL_API_KEY, or OPENROUTER_API_KEY."
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
    return {
        name: {
            "configured": bool(os.environ.get(config["key"])),
            "model": os.environ.get(config["model_env"], config["default_model"]),
            "cooldown_seconds": max(0.0, _PROVIDER_COOLDOWN_UNTIL.get(name, 0.0) - now),
        }
        for name, config in PROVIDERS.items()
    }
