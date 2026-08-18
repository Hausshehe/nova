"""Strict serialization helpers for AI-generated trading hypotheses.

The model may propose ideas, but it does not get to define what a valid
hypothesis means. This module converts one JSON object into the deterministic
Hypothesis contract and rejects ambiguous or extra fields.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from trading_research.contracts import Hypothesis


_ALLOWED_FIELDS = {
    "name",
    "thesis",
    "symbol",
    "timeframe",
    "rules",
    "expected_edge",
    "falsifier",
    "rationale",
}
_REQUIRED_FIELDS = _ALLOWED_FIELDS - {"rationale"}


def parse_hypothesis_json(payload: str | bytes) -> Hypothesis:
    """Parse one strict JSON hypothesis into the deterministic contract."""
    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"hypothesis JSON is invalid: {exc}") from exc

    if not isinstance(data, Mapping):
        raise ValueError("hypothesis JSON must contain one object")

    extra = sorted(set(data) - _ALLOWED_FIELDS)
    missing = sorted(_REQUIRED_FIELDS - set(data))
    if extra:
        raise ValueError("hypothesis contains unsupported fields: " + ", ".join(extra))
    if missing:
        raise ValueError("hypothesis is missing fields: " + ", ".join(missing))

    rules = data["rules"]
    if not isinstance(rules, Mapping) or not rules:
        raise ValueError("hypothesis rules must be a non-empty object")

    values = {
        "name": data["name"],
        "thesis": data["thesis"],
        "symbol": data["symbol"],
        "timeframe": data["timeframe"],
        "rules": {str(key): str(value) for key, value in rules.items()},
        "expected_edge": data["expected_edge"],
        "falsifier": data["falsifier"],
        "rationale": data.get("rationale", ""),
    }

    for field, value in values.items():
        if field != "rules" and not isinstance(value, str):
            raise ValueError(f"hypothesis field {field!r} must be a string")

    hypothesis = Hypothesis(**values)
    hypothesis.validate()
    return hypothesis


def hypothesis_to_json(hypothesis: Hypothesis) -> str:
    """Serialize a validated hypothesis deterministically."""
    hypothesis.validate()
    payload = {
        "name": hypothesis.name,
        "thesis": hypothesis.thesis,
        "symbol": hypothesis.symbol,
        "timeframe": hypothesis.timeframe,
        "rules": dict(sorted(hypothesis.rules.items())),
        "expected_edge": hypothesis.expected_edge,
        "falsifier": hypothesis.falsifier,
        "rationale": hypothesis.rationale,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
