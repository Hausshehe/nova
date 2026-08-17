"""Multi-provider AI router for Nova's adaptive planner.

Providers are optional. Nova uses whichever API keys are configured in the
Termux environment and automatically fails over on rate limits, transient
server errors, timeouts, or unavailable providers.

No provider-specific goal logic lives here: every provider receives the same
messages and generic tool schemas, so Nova remains adaptive.
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
    "cerebras": {
        "key": "CEREBRAS_API_KEY",
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "model_env": "CEREBRAS_MODEL",
        "default_model": "gpt-oss-120b",
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
        "default_model": "openai/gpt-oss-120b:free",
    },
}

DEFAULT_ORDER = ["gemini", "cerebras", "groq", "mistral", "openrouter"]
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _provider_order():
    configured = os.environ.get("AI_PROVIDER_ORDER", "").strip()
    if not configured:
        return DEFAULT_ORDER

    requested = [name.strip().lower() for name in configured.split(",") if name.strip()]
    return [name for name in requested if name in PROVIDERS]


def _delay(response, attempt):
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return max(0.5, float(retry_after)) + 0.2
        except ValueError:
            pass

    reset = response.headers.get("x-ratelimit-reset-tokens")
    if reset:
        value = reset.strip().lower()
        if value.endswith("s"):
            try:
                return max(0.5, float(value[:-1])) + 0.2
            except ValueError:
                pass

    return 1.0 * (2 ** attempt)


def _headers(provider, api_key):
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/Hausshehe/nova"
        headers["X-Title"] = "Nova Adaptive Android Agent"
    return headers


def _request(provider, messages, tools):
    config = PROVIDERS[provider]
    api_key = os.environ.get(config["key"])
    if not api_key:
        return None, f"{config['key']} is not configured"

    model = os.environ.get(config["model_env"], config["default_model"])
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 800,
        "tools": tools,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
    }

    # Gemini's OpenAI-compatible endpoint supports reasoning_effort and tool
    # calling, but we keep the shared payload conservative for portability.
    last_error = "unknown error"
    for attempt in range(3):
        try:
            response = requests.post(
                config["url"],
                headers=_headers(provider, api_key),
                json=payload,
                timeout=45,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < 2:
                time.sleep(1.0 * (2 ** attempt))
                continue
            return None, last_error

        if response.status_code == 200:
            try:
                data = response.json()
                return data["choices"][0]["message"], None
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                return None, f"{provider} returned an invalid response: {exc}"

        last_error = f"HTTP {response.status_code}: {response.text[:500]}"
        if response.status_code in RETRYABLE_STATUS and attempt < 2:
            delay = _delay(response, attempt)
            print(f"⏳ {provider} rate/transient limit; retrying in {delay:.1f}s...")
            time.sleep(delay)
            continue

        return None, last_error

    return None, last_error


def call_ai(messages, tools):
    """Return the first successful planner response from configured providers."""
    configured = []
    failures = []

    for provider in _provider_order():
        if os.environ.get(PROVIDERS[provider]["key"]):
            configured.append(provider)

    if not configured:
        raise RuntimeError(
            "No AI provider API keys are configured. Set at least one of "
            "GEMINI_API_KEY, GROQ_API_KEY, CEREBRAS_API_KEY, "
            "MISTRAL_API_KEY, or OPENROUTER_API_KEY."
        )

    for provider in configured:
        print(f"🤖 Planner provider: {provider}")
        message, error = _request(provider, messages, tools)
        if message is not None:
            return message
        failures.append(f"{provider}: {error}")
        print(f"⚠️ {provider} unavailable: {error}")

    raise RuntimeError("All configured AI providers failed. " + " | ".join(failures))


def provider_status():
    """Return a small diagnostic view of configured providers."""
    return {
        name: {
            "configured": bool(os.environ.get(config["key"])),
            "model": os.environ.get(config["model_env"], config["default_model"]),
        }
        for name, config in PROVIDERS.items()
    }
