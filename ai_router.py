"""Multi-provider AI router for Nova's adaptive planner.

Nova stays provider-agnostic: every provider receives the same messages and
same generic tool definitions. The router handles provider selection,
failover, rate-limit cooldowns, and conservative request compatibility.
"""

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
        "default_model": "@cf/openai/gpt-oss-120b",
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
        # Let OpenRouter select an available free model that supports the
        # request's capabilities instead of pinning Nova to a rotating model.
        "default_model": "openrouter/free",
    },
}

DEFAULT_ORDER = ["gemini", "groq", "cloudflare", "mistral", "openrouter"]
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

# Provider cooldowns live for the lifetime of Nova. A rate-limited provider is
# skipped temporarily instead of making Nova wait through repeated retries.
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
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": _max_output_tokens(),
        "tools": tools,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
    }

    # Fail over quickly. A single short retry is useful for transient network
    # failures, but rate limits and server overloads should move to the next
    # provider immediately rather than blocking Nova for a long retry cycle.
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
            # Do not sleep for provider-supplied retry-after values here. The
            # whole point of the multi-provider router is to fail over quickly.
            _mark_cooldown(provider, response.status_code)
            return None, error

        # Non-retryable errors normally indicate a bad key, unavailable model,
        # malformed request, or provider-specific incompatibility. Move on.
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
