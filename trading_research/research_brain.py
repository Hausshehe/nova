"""Researcher v1: structured research reasoning for Nova.

This layer teaches Nova how to think about a research problem before a
backtest is run. It does not execute experiments, change gates, or approve
strategies. Deterministic research code and the external assessor remain the
source of truth for evidence.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request


DEFAULT_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_COMPLETION_TOKENS = 4096


RESEARCH_BRAIN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "research_question": {"type": "string"},
        "mechanism": {"type": "string"},
        "hypothesis": {"type": "string"},
        "why_it_might_work": {"type": "string"},
        "what_would_falsify_it": {"type": "string"},
        "primary_test": {"type": "string"},
        "development_only_exploration": {"type": "array", "items": {"type": "string"}},
        "confirmation_rule": {"type": "string"},
        "key_risks": {"type": "array", "items": {"type": "string"}},
        "research_priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW", "REJECT"]},
        "next_action": {"type": "string", "enum": ["TEST", "EXPLORE", "REJECT", "CONFIRMATION_CANDIDATE"]},
    },
    "required": [
        "research_question",
        "mechanism",
        "hypothesis",
        "why_it_might_work",
        "what_would_falsify_it",
        "primary_test",
        "development_only_exploration",
        "confirmation_rule",
        "key_risks",
        "research_priority",
        "next_action",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ResearchQuestion:
    question: str
    symbol: str
    timeframe: str
    constraints: str = ""
    prior_findings: str = ""

    def validate(self) -> None:
        if not self.question.strip():
            raise ValueError("research question is required")
        if not self.symbol.strip():
            raise ValueError("research symbol is required")
        if not self.timeframe.strip():
            raise ValueError("research timeframe is required")


@dataclass(frozen=True)
class ResearchBrief:
    research_question: str
    mechanism: str
    hypothesis: str
    why_it_might_work: str
    what_would_falsify_it: str
    primary_test: str
    development_only_exploration: tuple[str, ...]
    confirmation_rule: str
    key_risks: tuple[str, ...]
    research_priority: str
    next_action: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResearchBrief":
        required = (
            "research_question",
            "mechanism",
            "hypothesis",
            "why_it_might_work",
            "what_would_falsify_it",
            "primary_test",
            "development_only_exploration",
            "confirmation_rule",
            "key_risks",
            "research_priority",
            "next_action",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError("research brief missing fields: " + ",".join(missing))
        exploration = payload["development_only_exploration"]
        risks = payload["key_risks"]
        if not isinstance(exploration, list) or not all(isinstance(x, str) and x.strip() for x in exploration):
            raise ValueError("development_only_exploration must be a non-empty-string list")
        if not isinstance(risks, list) or not all(isinstance(x, str) and x.strip() for x in risks):
            raise ValueError("key_risks must be a non-empty-string list")
        priority = str(payload["research_priority"]).upper()
        action = str(payload["next_action"]).upper()
        if priority not in {"HIGH", "MEDIUM", "LOW", "REJECT"}:
            raise ValueError("invalid research_priority")
        if action not in {"TEST", "EXPLORE", "REJECT", "CONFIRMATION_CANDIDATE"}:
            raise ValueError("invalid next_action")
        strings = [payload[key] for key in required if key not in {"development_only_exploration", "key_risks"}]
        if not all(isinstance(value, str) and value.strip() for value in strings):
            raise ValueError("research brief contains empty text fields")
        return cls(
            research_question=str(payload["research_question"]),
            mechanism=str(payload["mechanism"]),
            hypothesis=str(payload["hypothesis"]),
            why_it_might_work=str(payload["why_it_might_work"]),
            what_would_falsify_it=str(payload["what_would_falsify_it"]),
            primary_test=str(payload["primary_test"]),
            development_only_exploration=tuple(exploration),
            confirmation_rule=str(payload["confirmation_rule"]),
            key_risks=tuple(risks),
            research_priority=priority,
            next_action=action,
        )


Transport = Callable[[dict[str, Any]], dict[str, Any]]


def build_research_brain_prompt(question: ResearchQuestion) -> str:
    question.validate()
    prior = question.prior_findings.strip() or "No prior findings."
    constraints = question.constraints.strip() or "None."
    schema_text = json.dumps(RESEARCH_BRAIN_SCHEMA, ensure_ascii=False, separators=(",", ":"))
    return f"""
You are Nova Researcher v1. Your job is to design serious market research, not
manufacture a profitable backtest.

Research question: {question.question}
Symbol: {question.symbol}
Timeframe: {question.timeframe}
Constraints: {constraints}
Prior findings: {prior}

Research constitution:
1. Start from a plausible market mechanism, not a random indicator mixture.
2. State one falsifiable hypothesis.
3. Separate discovery from confirmation.
4. Exploration is allowed only on development data. Confirmation data must
   remain untouched until the formulation is locked.
5. Every meaningful variant is part of the research genealogy.
6. A failed formulation does not automatically kill the underlying mechanism.
7. Repeated optimization can discover candidates, but it increases skepticism
   and cannot be presented as independent evidence.
8. Never change costs, gates, or the definition of success just to rescue a
   failed idea.
9. "No edge found" is a valid result.
10. Do not claim that a candidate is a real edge. The evidence must earn that
    conclusion through fresh confirmation and later replication.
11. Prefer adaptive, regime-aware research when a fixed universal strategy
    would be implausible.
12. Do not provide live-trading execution instructions.

Return exactly one JSON object matching this schema. Do not add commentary:
{schema_text}
""".strip()


def _default_transport(api_key: str, endpoint: str, timeout: float) -> Transport:
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


class ResearchBrain:
    """Generate a structured, evidence-first research brief.

    The brain only proposes research. It cannot run a backtest, edit gates,
    select confirmation data, or approve a strategy.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        endpoint: str | None = None,
        timeout: float = 45.0,
        transport: Transport | None = None,
    ) -> None:
        resolved_key = (api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")).strip()
        resolved_model = (model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)).strip()
        resolved_endpoint = (endpoint or os.environ.get("GROQ_URL", DEFAULT_ENDPOINT)).strip()
        if not resolved_key:
            raise ValueError("GROQ_API_KEY is required")
        if not resolved_model:
            raise ValueError("Groq model is required")
        if not resolved_endpoint:
            raise ValueError("Groq endpoint is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.model = resolved_model
        self.endpoint = resolved_endpoint
        self._transport = transport or _default_transport(resolved_key, resolved_endpoint, timeout)

    def _request(self, *, structured: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return exactly one structured research brief as JSON."},
                {"role": "user", "content": build_research_brain_prompt(self._question)},
            ],
            "temperature": 0.2,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "reasoning_effort": "low",
            "reasoning_format": "hidden",
        }
        if structured:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "nova_research_brief",
                    "strict": True,
                    "schema": RESEARCH_BRAIN_SCHEMA,
                },
            }
        else:
            payload["response_format"] = {"type": "json_object"}
        return self._transport(payload)

    def investigate(self, question: ResearchQuestion) -> ResearchBrief:
        question.validate()
        self._question = question
        try:
            response = self._request(structured=True)
        except RuntimeError as exc:
            # Some Groq environments can reject strict structured output even
            # when the model itself is available. Fall back to JSON Object Mode,
            # then validate the exact same schema locally.
            if "HTTP 403" not in str(exc):
                raise
            response = self._request(structured=False)

        try:
            content = response["choices"][0]["message"].get("content", "")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Groq response contained no visible JSON content")
            data = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("Groq response did not contain valid structured research JSON") from exc
        return ResearchBrief.from_dict(data)
