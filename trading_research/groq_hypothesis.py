"""Groq-backed hypothesis proposal adapter.

The model is a proposal source only. Its output is validated into Nova's
strict Hypothesis contract before the Researcher can reserve budget for it.
No model response can alter research gates or grant execution authority.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request

from .hypothesis_io import parse_hypothesis_json
from .researcher import HypothesisProposal


DEFAULT_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"


HYPOTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "thesis": {"type": "string"},
        "symbol": {"type": "string"},
        "timeframe": {"type": "string"},
        "rules": {
            "type": "object",
            "properties": {
                "entry": {"type": "string"},
                "exit": {"type": "string"},
                "filters": {"type": "string"},
                "costs": {"type": "string"},
            },
            "required": ["entry", "exit", "filters", "costs"],
            "additionalProperties": False,
        },
        "expected_edge": {"type": "string"},
        "falsifier": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": [
        "name",
        "thesis",
        "symbol",
        "timeframe",
        "rules",
        "expected_edge",
        "falsifier",
        "rationale",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ResearchQuestion:
    question: str
    symbol: str
    timeframe: str
    constraints: str = ""

    def validate(self) -> None:
        if not self.question.strip():
            raise ValueError("research question is required")
        if not self.symbol.strip():
            raise ValueError("research symbol is required")
        if not self.timeframe.strip():
            raise ValueError("research timeframe is required")


Transport = Callable[[dict[str, Any]], dict[str, Any]]


def build_research_prompt(question: ResearchQuestion, prior_context: str = "") -> str:
    question.validate()
    context = prior_context.strip() or "No prior research context was supplied."
    return (
        "You are Nova's research hypothesis generator. Propose exactly one "
        "falsifiable trading hypothesis. Do not claim success. Do not provide "
        "execution instructions, account actions, order sizes, live-trading "
        "commands, or changes to research gates. The hypothesis must be "
        "testable with deterministic OHLCV rules and must explicitly state a "
        "falsifier. Avoid duplicating prior research.\n\n"
        f"Research question: {question.question}\n"
        f"Symbol: {question.symbol}\n"
        f"Timeframe: {question.timeframe}\n"
        f"Constraints: {question.constraints or 'none'}\n\n"
        f"Prior research context:\n{context}"
    )


def _default_transport(api_key: str, model: str, endpoint: str, timeout: float) -> Transport:
    def send(payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Groq API HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Groq API network failure: {exc.reason}") from exc

    return send


class GroqHypothesisGenerator:
    """Generate one structured hypothesis from Groq without adding dependencies."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Groq API key is required")
        if not model.strip():
            raise ValueError("Groq model is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.model = model
        self.endpoint = endpoint
        self._transport = transport or _default_transport(api_key, model, endpoint, timeout)

    def propose(self, question: ResearchQuestion, prior_context: str = "") -> HypothesisProposal:
        prompt = build_research_prompt(question, prior_context)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return exactly one research hypothesis as structured JSON."
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "nova_trading_hypothesis",
                    "strict": True,
                    "schema": HYPOTHESIS_SCHEMA,
                },
            },
        }
        response = self._transport(payload)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Groq response missing structured hypothesis content") from exc

        hypothesis = parse_hypothesis_json(content)
        return HypothesisProposal(hypothesis=hypothesis, source=f"groq:{self.model}")
