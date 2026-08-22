"""Mechanism-first Research Brain v2.

This module separates research-space generation from experiment selection.
It deliberately avoids hard-coding a trading strategy family. The model must
propose competing mechanisms, predict how they differ, identify confounders,
and select a high-information experiment while respecting ResearchState.

Deterministic state rules remain authoritative; this layer only proposes
research decisions for external assessment and downstream validation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request

from trading_research.research_state import ResearchState

DEFAULT_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_COMPLETION_TOKENS = 6144
HTTP_USER_AGENT = "NovaResearcher/2.0"

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "problem_interpretation": {"type": "string"},
        "premise_challenges": {"type": "array", "items": {"type": "string"}, "minItems": 2},
        "mechanisms": {
            "type": "array",
            "minItems": 2,
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "mechanism": {"type": "string"},
                    "causal_story": {"type": "string"},
                    "prediction": {"type": "string"},
                    "disconfirming_observation": {"type": "string"},
                    "current_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "status": {"type": "string", "enum": ["candidate", "weakened", "rejected", "surviving"]},
                    "why_testable": {"type": "string"},
                },
                "required": ["id", "mechanism", "causal_story", "prediction", "disconfirming_observation", "current_confidence", "status", "why_testable"],
                "additionalProperties": False,
            },
        },
        "experiment_candidates": {
            "type": "array",
            "minItems": 2,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "question_discriminated": {"type": "string"},
                    "mechanisms_separated": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                    "outcome": {"type": "string"},
                    "horizon": {"type": "string"},
                    "development_only": {"type": "boolean"},
                    "estimated_information_value": {"type": "number", "minimum": 0, "maximum": 1},
                    "estimated_cost": {"type": "number", "minimum": 0, "maximum": 1},
                    "overfitting_risk": {"type": "number", "minimum": 0, "maximum": 1},
                    "confounders": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                },
                "required": ["id", "name", "question_discriminated", "mechanisms_separated", "outcome", "horizon", "development_only", "estimated_information_value", "estimated_cost", "overfitting_risk", "confounders"],
                "additionalProperties": False,
            },
        },
        "selected_experiment_id": {"type": "string"},
        "selection_rationale": {"type": "string"},
        "falsification_rule": {"type": "string"},
        "stopping_rule": {"type": "string"},
        "confirmation_protection": {"type": "string"},
        "next_action": {"type": "string", "enum": ["TEST", "EXPLORE", "REJECT", "STOP", "CONFIRMATION_CANDIDATE"]},
        "state_update_expectation": {"type": "string"},
    },
    "required": ["question", "problem_interpretation", "premise_challenges", "mechanisms", "experiment_candidates", "selected_experiment_id", "selection_rationale", "falsification_rule", "stopping_rule", "confirmation_protection", "next_action", "state_update_expectation"],
    "additionalProperties": False,
}

@dataclass(frozen=True)
class ResearchRequest:
    question: str
    symbol: str
    timeframe: str
    constraints: str = ""

    def validate(self) -> None:
        for name, value in (("question", self.question), ("symbol", self.symbol), ("timeframe", self.timeframe)):
            if not value.strip():
                raise ValueError(f"{name} is required")

Transport = Callable[[dict[str, Any]], dict[str, Any]]


def _state_context(state: ResearchState) -> dict[str, Any]:
    return state.to_dict()


def build_prompt(request_data: ResearchRequest, state: ResearchState) -> str:
    request_data.validate()
    context = json.dumps(_state_context(state), ensure_ascii=False, indent=2)
    return f"""
You are Nova Researcher v2. You are a research partner, not a strategy generator.

Research question: {request_data.question}
Symbol: {request_data.symbol}
Timeframe: {request_data.timeframe}
Constraints: {request_data.constraints or 'None'}

Current structured research state:
{context}

Research constitution:
1. First determine what the question actually asks. Challenge the premise before proposing trades.
2. Generate at least two genuinely different causal mechanisms. Do not create cosmetic indicator variants and call them mechanisms.
3. Use prior evidence in the state. A failed implementation weakens an implementation, not automatically the causal mechanism; repeated independent failures should reduce confidence and narrow the search space.
4. Never repeat a prohibited or already-tested experiment merely with renamed parameters.
5. Separate mechanism tests from implementation optimization.
6. An experiment is valuable when its outcome meaningfully distinguishes competing explanations, not merely because it may produce a high backtest return.
7. Estimate information value, research cost, and overfitting risk for candidate experiments.
8. Pick one next experiment only after considering alternatives.
9. State exactly what observation would falsify the selected hypothesis or make further work unjustified.
10. Define a stopping rule. STOP is legitimate.
11. Development evidence cannot be treated as confirmation. Confirmation data remain untouched until a formulation is locked.
12. Do not claim a real edge. The output is a research decision, not a trading recommendation.
13. The model cannot alter external gates, costs, or confirmation policy.
14. Preserve uncertainty; do not turn a failed test into false certainty about a mechanism.

Return exactly one JSON object matching the schema. No commentary.
{json.dumps(SCHEMA, ensure_ascii=False, separators=(',', ':'))}
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
                "Accept": "application/json",
                "User-Agent": HTTP_USER_AGENT,
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


def validate_decision(payload: dict[str, Any], state: ResearchState) -> dict[str, Any]:
    required = set(SCHEMA["required"])
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError("decision missing fields: " + ",".join(missing))
    mechanisms = payload["mechanisms"]
    experiments = payload["experiment_candidates"]
    if not isinstance(mechanisms, list) or len(mechanisms) < 2:
        raise ValueError("at least two mechanisms are required")
    if not isinstance(experiments, list) or len(experiments) < 2:
        raise ValueError("at least two experiment candidates are required")
    mechanism_ids = {str(item["id"]) for item in mechanisms}
    if len(mechanism_ids) != len(mechanisms):
        raise ValueError("mechanism ids must be unique")
    ids = {str(item["id"]) for item in experiments}
    if len(ids) != len(experiments):
        raise ValueError("experiment ids must be unique")
    selected = str(payload["selected_experiment_id"])
    if selected not in ids:
        raise ValueError("selected experiment is not among candidates")
    tested = set(state.tested_experiments)
    if selected in tested:
        raise ValueError("selected experiment has already been tested")
    if selected in set(state.prohibited_experiments):
        raise ValueError("selected experiment is prohibited by research state")
    if state.confirmation_locked and payload["next_action"] not in {"STOP", "CONFIRMATION_CANDIDATE"}:
        raise ValueError("confirmation is locked; development research cannot continue")
    for experiment in experiments:
        separated = {str(x) for x in experiment["mechanisms_separated"]}
        if len(separated) < 2:
            raise ValueError("each experiment must separate at least two mechanisms")
        if not separated.issubset(mechanism_ids):
            raise ValueError("experiment references unknown mechanism ids")
        if not experiment["development_only"] and payload["next_action"] not in {"CONFIRMATION_CANDIDATE", "STOP"}:
            raise ValueError("non-development experiments require confirmation state")
    return payload


class ResearchBrainV2:
    def __init__(self, api_key: str | None = None, *, model: str | None = None, endpoint: str | None = None, timeout: float = 45.0, transport: Transport | None = None) -> None:
        key = (api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")).strip()
        self.model = (model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)).strip()
        self.endpoint = (endpoint or os.environ.get("GROQ_URL", DEFAULT_ENDPOINT)).strip()
        if not key and transport is None:
            raise ValueError("GROQ_API_KEY is required")
        if not self.model or not self.endpoint or timeout <= 0:
            raise ValueError("invalid model, endpoint, or timeout")
        self._transport = transport or _default_transport(key, self.endpoint, timeout)

    def decide(self, request_data: ResearchRequest, state: ResearchState) -> dict[str, Any]:
        prompt = build_prompt(request_data, state)
        response = self._transport({
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return exactly one JSON research decision."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.15,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "response_format": {"type": "json_schema", "json_schema": {"name": "nova_research_decision_v2", "strict": True, "schema": SCHEMA}},
        })
        content = response["choices"][0]["message"]["content"]
        payload = json.loads(content) if isinstance(content, str) else content
        return validate_decision(payload, state)
