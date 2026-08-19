"""Time-bounded trading-experience context for future decisions.

This module retrieves only experience that existed at the decision timestamp.
It is context only: it never authorizes execution or changes a strategy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .decision_outcome import DecisionOutcomeStore
from .decision_provenance import DecisionProvenanceStore


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_utc(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


@dataclass(frozen=True)
class TradingExperienceContext:
    strategy_name: str
    strategy_version: str
    as_of_utc: str
    prior_decisions: tuple[dict[str, Any], ...]
    prior_outcomes: tuple[dict[str, Any], ...]

    @property
    def context_hash(self) -> str:
        payload = {
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "as_of_utc": self.as_of_utc,
            "prior_decisions": list(self.prior_decisions),
            "prior_outcomes": list(self.prior_outcomes),
        }
        return _sha256(_canonical_json(payload))


class TradingExperienceContextBuilder:
    """Build causal, bounded context from Nova's recorded trading experience."""

    def __init__(self, decision_store: DecisionProvenanceStore, outcome_store: DecisionOutcomeStore):
        self.decision_store = decision_store
        self.outcome_store = outcome_store

    def build(
        self,
        *,
        strategy_name: str,
        strategy_version: str,
        as_of_utc: str,
        max_decisions: int = 20,
        max_outcomes: int = 20,
    ) -> TradingExperienceContext:
        if not strategy_name.strip() or not strategy_version.strip():
            raise ValueError("strategy identity is required")
        cutoff = _parse_utc(as_of_utc)
        if max_decisions <= 0 or max_outcomes <= 0:
            raise ValueError("context limits must be positive")

        decisions = []
        outcomes = []
        for decision in self.decision_store.list_for_strategy(strategy_name, strategy_version):
            decided_at = _parse_utc(decision.decided_at_utc)
            if decided_at >= cutoff:
                continue
            decisions.append(
                {
                    "decision_id": decision.decision_id,
                    "decided_at_utc": decision.decided_at_utc,
                    "action": decision.action,
                    "rationale": decision.rationale,
                    "hypothesis_fingerprint": decision.hypothesis_fingerprint,
                    "dataset_sha256": decision.dataset_sha256,
                    "approval_status": decision.approval_status,
                    "risk_snapshot": decision.risk_snapshot,
                }
            )
            for outcome in self.outcome_store.list_for_decision(decision.decision_id):
                recorded_at = _parse_utc(outcome.recorded_at_utc)
                if recorded_at >= cutoff:
                    continue
                outcomes.append(
                    {
                        "outcome_id": outcome.outcome_id,
                        "decision_id": outcome.decision_id,
                        "trade_id": outcome.trade_id,
                        "recorded_at_utc": outcome.recorded_at_utc,
                        "outcome": outcome.outcome,
                        "realized_pnl": outcome.realized_pnl,
                        "attribution": outcome.attribution,
                        "lesson": outcome.lesson,
                        "execution_summary": outcome.execution_summary,
                    }
                )

        decisions.sort(key=lambda item: (item["decided_at_utc"], item["decision_id"]), reverse=True)
        outcomes.sort(key=lambda item: (item["recorded_at_utc"], item["outcome_id"]), reverse=True)

        return TradingExperienceContext(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            as_of_utc=as_of_utc,
            prior_decisions=tuple(decisions[:max_decisions]),
            prior_outcomes=tuple(outcomes[:max_outcomes]),
        )
