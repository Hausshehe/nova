"""Structured AI recommendation contract with deterministic policy validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


_ALLOWED_ACTIONS = {"NO_ACTION", "WATCH", "ENTER", "EXIT"}
_ALLOWED_URGENCY = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


@dataclass(frozen=True)
class AIRecommendation:
    action: str
    strategy_name: str | None
    strategy_version: str | None
    rationale: str
    urgency: str
    confidence: float

    def validate(self) -> None:
        if self.action not in _ALLOWED_ACTIONS:
            raise ValueError(f"unsupported action: {self.action}")
        if self.urgency not in _ALLOWED_URGENCY:
            raise ValueError(f"unsupported urgency: {self.urgency}")
        if not self.rationale.strip():
            raise ValueError("rationale is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.action in {"ENTER", "EXIT"} and not self.strategy_name:
            raise ValueError("strategy_name is required for ENTER/EXIT")


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": sorted(_ALLOWED_ACTIONS)},
        "strategy_name": {"type": ["string", "null"]},
        "strategy_version": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
        "urgency": {"type": "string", "enum": sorted(_ALLOWED_URGENCY)},
        "confidence": {"type": "number"},
    },
    "required": [
        "action",
        "strategy_name",
        "strategy_version",
        "rationale",
        "urgency",
        "confidence",
    ],
    "additionalProperties": False,
}


def parse_recommendation(value: str | dict[str, Any]) -> AIRecommendation:
    payload = json.loads(value) if isinstance(value, str) else dict(value)
    expected = set(SCHEMA["required"])
    extra = set(payload) - expected
    missing = expected - set(payload)
    if extra:
        raise ValueError("unsupported fields: " + ", ".join(sorted(extra)))
    if missing:
        raise ValueError("missing fields: " + ", ".join(sorted(missing)))

    recommendation = AIRecommendation(
        action=str(payload["action"]),
        strategy_name=payload["strategy_name"],
        strategy_version=payload["strategy_version"],
        rationale=str(payload["rationale"]),
        urgency=str(payload["urgency"]),
        confidence=float(payload["confidence"]),
    )
    recommendation.validate()
    return recommendation


def recommendation_to_json(recommendation: AIRecommendation) -> str:
    recommendation.validate()
    return json.dumps(
        {
            "action": recommendation.action,
            "strategy_name": recommendation.strategy_name,
            "strategy_version": recommendation.strategy_version,
            "rationale": recommendation.rationale,
            "urgency": recommendation.urgency,
            "confidence": recommendation.confidence,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
