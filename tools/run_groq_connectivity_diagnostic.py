#!/usr/bin/env python3
"""Diagnose Groq connectivity without touching Nova research behavior.

Checks DNS/TLS reachability, unauthenticated and authenticated model-list calls,
and one tiny chat-completions request. Never prints the API key.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import time
from urllib import error, request

BASE = "https://api.groq.com/openai/v1"
MODELS_URL = f"{BASE}/models"
CHAT_URL = f"{BASE}/chat/completions"


def _request(url: str, *, method: str = "GET", api_key: str | None = None, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": "Nova-Groq-Diagnostic/1.0", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method=method)
    started = time.monotonic()
    try:
        with request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {"ok": True, "status": response.status, "elapsed_ms": round((time.monotonic()-started)*1000, 1), "headers": {k.lower(): v for k, v in response.headers.items() if k.lower() in {"server", "cf-ray", "content-type", "retry-after"}}, "body": raw[:1000]}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "elapsed_ms": round((time.monotonic()-started)*1000, 1), "headers": {k.lower(): v for k, v in exc.headers.items() if k.lower() in {"server", "cf-ray", "content-type", "retry-after"}}, "body": raw[:1000]}
    except Exception as exc:
        return {"ok": False, "status": None, "elapsed_ms": round((time.monotonic()-started)*1000, 1), "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GROQ_API_KEY is not set")

    host = "api.groq.com"
    dns = None
    try:
        dns = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        dns_result = {"ok": True, "addresses": sorted({item[4][0] for item in dns})}
    except Exception as exc:
        dns_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    tls_result = {"ok": False}
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                tls_result = {"ok": True, "version": ssock.version(), "cipher": ssock.cipher()[0] if ssock.cipher() else None}
    except Exception as exc:
        tls_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    unauth = _request(MODELS_URL)
    auth = _request(MODELS_URL, api_key=api_key)
    chat = _request(CHAT_URL, method="POST", api_key=api_key, payload={"model": args.model, "messages":[{"role":"user","content":"Reply with exactly: OK"}],"temperature":0,"max_tokens":4})

    result = {
        "policy": "isolated_groq_connectivity_diagnostic",
        "endpoint": BASE,
        "model_tested": args.model,
        "dns": dns_result,
        "tls": tls_result,
        "unauthenticated_models_request": unauth,
        "authenticated_models_request": auth,
        "authenticated_minimal_chat_request": chat,
        "interpretation": {
            "403_with_cloudflare_headers_or_1010": "Likely edge/network/policy block before normal model inference; not a Nova prompt issue.",
            "401_on_authenticated_request": "API key is missing/invalid/expired or not accepted.",
            "200_models_but_chat_403": "Authentication works; investigate model/project permissions or chat-specific policy.",
            "200_chat": "Groq connectivity and authentication are working; the earlier equivalence runner failure is elsewhere.",
        },
    }
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        from pathlib import Path
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
