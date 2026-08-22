"""Mechanism-first Research Brain v2.

The model performs research reasoning and emits JSON. Nova itself enforces the
full research contract locally so provider-side constrained decoding cannot
become the bottleneck for complex research decisions.
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
MAX_COMPLETION_TOKENS = 5000
HTTP_USER_AGENT = "NovaResearcher/2.0"

# Internal contract. This is intentionally not sent as a provider-side JSON
# schema. Provider JSON mode guarantees valid JSON; Nova enforces the complete
# research contract locally in validate_decision().
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "problem_interpretation": {"type": "string"},
        "premise_challenges": {"type": "array", "items": {"type": "string"}},
        "mechanisms": {"type": "array"},
        "experiment_candidates": {"type": "array"},
        "selected_experiment_id": {"type": "string"},
        "selection_rationale": {"type": "string"},
        "falsification_rule": {"type": "string"},
        "stopping_rule": {"type": "string"},
        "confirmation_protection": {"type": "string"},
        "next_action": {"type": "string"},
        "state_update_expectation": {"type": "string"},
    },
    "required": [
        "question", "problem_interpretation", "premise_challenges", "mechanisms",
        "experiment_candidates", "selected_experiment_id", "selection_rationale",
        "falsification_rule", "stopping_rule", "confirmation_protection",
        "next_action", "state_update_expectation",
    ],
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
    context = json.dumps(_state_context(state), ensure_ascii=False, separators=(",", ":"))
    return f"""You are Nova Researcher v2. You are a research partner, not a strategy generator.

Research question: {request_data.question}
Symbol: {request_data.symbol}
Timeframe: {request_data.timeframe}
Constraints: {request_data.constraints or 'None'}

Current structured research state:
{context}

Research constitution:
1. Determine what the question actually asks and challenge its premise before proposing trades.
2. Generate at least two genuinely different causal mechanisms. Do not use cosmetic indicator variants as mechanisms.
3. Use prior evidence. A failed implementation weakens an implementation, not automatically the mechanism; repeated independent failures should reduce confidence and narrow the search space.
4. Never repeat a prohibited or already-tested experiment, even with renamed parameters.
5. Separate mechanism tests from implementation optimization.
6. Prefer experiments whose outcomes distinguish competing explanations, not merely experiments likely to produce high returns.
7. Estimate information value, research cost, and overfitting risk.
8. Consider alternatives before selecting one next experiment.
9. State what observation would falsify the selected hypothesis or make further work unjustified.
10. Define a stopping rule. STOP is legitimate.
11. Development evidence is not confirmation. Confirmation data remain untouched until a formulation is locked.
12. Do not claim a real edge. This is a research decision, not a trading recommendation.
13. Do not alter external gates, costs, or confirmation policy.
14. Preserve uncertainty; do not turn failed tests into false certainty.

Return exactly one valid JSON object. Use these top-level fields exactly:
question, problem_interpretation, premise_challenges, mechanisms, experiment_candidates,
selected_experiment_id, selection_rationale, falsification_rule, stopping_rule,
confirmation_protection, next_action, state_update_expectation.
Do not output markdown, commentary, or any text outside the JSON object.""".strip()


def _default_transport(api_key: str, endpoint: str, timeout: float) -> Transport:
    def send(payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(endpoint, data=body, headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": HTTP_USER_AGENT,
        }, method="POST")
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
    mechanisms, experiments = payload["mechanisms"], payload["experiment_candidates"]
    if not isinstance(mechanisms, list) or len(mechanisms) < 2 or len(mechanisms) > 6:
        raise ValueError("between 2 and 6 mechanisms are required")
    if not isinstance(experiments, list) or len(experiments) < 2 or len(experiments) > 5:
        raise ValueError("between 2 and 5 experiment candidates are required")
    if not isinstance(payload["premise_challenges"], list) or len(payload["premise_challenges"]) < 2:
        raise ValueError("at least two premise challenges are required")
    mechanism_ids = set()
    for mechanism in mechanisms:
        if not isinstance(mechanism, dict):
            raise ValueError("each mechanism must be an object")
        for key in ("id", "mechanism", "causal_story", "prediction", "disconfirming_observation", "current_confidence", "status", "why_testable"):
            if key not in mechanism:
                raise ValueError(f"mechanism missing field: {key}")
        mid = str(mechanism["id"])
        mechanism_ids.add(mid)
        confidence = mechanism["current_confidence"]
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("mechanism confidence must be between 0 and 1")
        if mechanism["status"] not in {"candidate", "weakened", "rejected", "surviving"}:
            raise ValueError("invalid mechanism status")
    if len(mechanism_ids) != len(mechanisms):
        raise ValueError("mechanism ids must be unique")

    experiment_ids = set()
    for experiment in experiments:
        if not isinstance(experiment, dict):
            raise ValueError("each experiment must be an object")
        for key in ("id", "name", "question_discriminated", "mechanisms_separated", "outcome", "horizon", "development_only", "estimated_information_value", "estimated_cost", "overfitting_risk", "confounders"):
            if key not in experiment:
                raise ValueError(f"experiment missing field: {key}")
        eid = str(experiment["id"])
        experiment_ids.add(eid)
        separated = {str(x) for x in experiment["mechanisms_separated"]}
        if len(separated) < 2:
            raise ValueError("each experiment must separate at least two mechanisms")
        if not separated.issubset(mechanism_ids):
            raise ValueError("experiment references unknown mechanism ids")
        if not isinstance(experiment["confounders"], list) or len(experiment["confounders"]) < 1:
            raise ValueError("each experiment must identify at least one confounder")
        for field in ("estimated_information_value", "estimated_cost", "overfitting_risk"):
            value = experiment[field]
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError(f"{field} must be between 0 and 1")
        if not isinstance(experiment["development_only"], bool):
            raise ValueError("development_only must be boolean")
    if len(experiment_ids) != len(experiments):
        raise ValueError("experiment ids must be unique")

    selected = str(payload["selected_experiment_id"])
    if selected not in experiment_ids:
        raise ValueError("selected experiment is not among candidates")
    if selected in set(state.tested_experiments):
        raise ValueError("selected experiment has already been tested")
    if selected in set(state.prohibited_experiments):
        raise ValueError("selected experiment is prohibited by research state")
    if state.confirmation_locked and payload["next_action"] not in {"STOP", "CONFIRMATION_CANDIDATE"}:
        raise ValueError("confirmation is locked; development research cannot continue")
    if payload["next_action"] not in {"TEST", "EXPLORE", "REJECT", "STOP", "CONFIRMATION_CANDIDATE"}:
        raise ValueError("invalid next_action")
    for experiment in experiments:
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
                {"role": "system", "content": "Return exactly one valid JSON object and nothing else."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.15,
            "reasoning_effort": "high",
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "response_format": {"type": "json_object"},
        })
        content = response["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Groq returned empty JSON content")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Groq returned malformed JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Groq returned a non-object JSON value")
        return validate_decision(payload, state)
