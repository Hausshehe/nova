"""Bounded AI reasoning for escalated market events.

Python market observation decides when an event deserves attention. This
module packages that event into a small structured request for an LLM.
The response is advisory only: it cannot authorize execution or modify
research gates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request

from .market_monitor import MarketEvent

DEFAULT_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"


@dataclass(frozen=True)
class MarketAnalysis:
    assessment: str
    rationale: str
    relevant_strategies: tuple[str, ...] = ()
    urgency: str = "NORMAL"

    def validate(self) -> None:
        if self.assessment not in {"NO_ACTION", "WATCH", "SETUP", "RISK"}:
            raise ValueError("unsupported assessment")
        if self.urgency not in {"NORMAL", "ELEVATED", "CRITICAL"}:
            raise ValueError("unsupported urgency")
        if not self.rationale.strip():
            raise ValueError("analysis rationale is required")
        if any(not item.strip() for item in self.relevant_strategies):
            raise ValueError("strategy names must be non-empty")


Transport = Callable[[dict[str, Any]], dict[str, Any]]


def _default_transport(api_key: str, model: str, endpoint: str, timeout: float) -> Transport:
    def send(payload: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
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


class GroqMarketReasoner:
    """Ask Groq to classify an escalated event without granting execution authority."""

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
        self.model = model
        self.endpoint = endpoint
        self._transport = transport or _default_transport(api_key, model, endpoint, timeout)

    def analyze(
        self,
        event: MarketEvent,
        *,
        strategy_context: str = "",
        market_context: str = "",
    ) -> MarketAnalysis:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Nova's market event analyst. Classify the event only. "
                        "Do not place trades, choose position size, alter risk gates, "
                        "or claim profitability. Return exactly the requested JSON object."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Event type: {event.event_type}\n"
                        f"Symbol: {event.symbol}\n"
                        f"Timeframe: {event.timeframe}\n"
                        f"Timestamp: {event.timestamp.isoformat()}\n"
                        f"Price: {event.price}\n"
                        f"Change bps: {event.change_bps}\n"
                        f"Spread bps: {event.spread_bps}\n"
                        f"Reason: {event.reason}\n\n"
                        f"Market context:\n{market_context or 'none'}\n\n"
                        f"Approved-strategy context:\n{strategy_context or 'none'}"
                    ),
                },
            ],
            "temperature": 0.1,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "nova_market_analysis",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "assessment": {
                                "type": "string",
                                "enum": ["NO_ACTION", "WATCH", "SETUP", "RISK"],
                            },
                            "rationale": {"type": "string"},
                            "relevant_strategies": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "urgency": {
                                "type": "string",
                                "enum": ["NORMAL", "ELEVATED", "CRITICAL"],
                            },
                        },
                        "required": [
                            "assessment",
                            "rationale",
                            "relevant_strategies",
                            "urgency",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
        }
        response = self._transport(payload)
        try:
            content = response["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError("Groq response missing structured market analysis") from exc

        analysis = MarketAnalysis(
            assessment=str(data["assessment"]),
            rationale=str(data["rationale"]),
            relevant_strategies=tuple(str(item) for item in data["relevant_strategies"]),
            urgency=str(data["urgency"]),
        )
        analysis.validate()
        return analysis
