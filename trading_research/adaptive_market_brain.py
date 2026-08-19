"""Bridge deterministic market escalation, AI reasoning, and policy validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .decision_policy import PolicyDecision
from .escalation import AdaptiveEscalator, EscalationDecision
from .market_monitor import MarketEvent
from .market_reasoner import GroqMarketReasoner, MarketAnalysis


@dataclass(frozen=True)
class AdaptiveMarketResult:
    escalation: EscalationDecision
    analysis: MarketAnalysis | None
    policy_decision: PolicyDecision | None = None


class AdaptiveMarketBrain:
    """Use Python for observation, Groq for reasoning, and policy for authorization."""

    def __init__(
        self,
        escalator: AdaptiveEscalator,
        reasoner: GroqMarketReasoner | None = None,
        strategy_context_provider: Callable[[MarketEvent], str] | None = None,
        market_context_provider: Callable[[MarketEvent], str] | None = None,
        recommendation_policy: Callable[[object], PolicyDecision] | None = None,
    ) -> None:
        self.escalator = escalator
        self.reasoner = reasoner
        self.strategy_context_provider = strategy_context_provider
        self.market_context_provider = market_context_provider
        self.recommendation_policy = recommendation_policy

    def process(self, event: MarketEvent, *, market_context: str = "") -> AdaptiveMarketResult:
        decision = self.escalator.evaluate(event)
        if not decision.request_ai or self.reasoner is None:
            return AdaptiveMarketResult(decision, None, None)

        strategy_context = (
            self.strategy_context_provider(event)
            if self.strategy_context_provider is not None
            else ""
        )
        if market_context:
            retrieved_market_context = market_context
        elif self.market_context_provider is not None:
            retrieved_market_context = self.market_context_provider(event)
        else:
            retrieved_market_context = ""

        analysis = self.reasoner.analyze(
            event,
            market_context=retrieved_market_context,
            strategy_context=strategy_context,
        )
        policy_decision = None
        if analysis.recommendation is not None and self.recommendation_policy is not None:
            policy_decision = self.recommendation_policy(analysis.recommendation)
        return AdaptiveMarketResult(decision, analysis, policy_decision)


def strategy_context_from_records(
    records: Iterable[dict],
    *,
    symbol: str,
    timeframe: str,
) -> str:
    """Build compact context from approved strategy records only."""
    lines: list[str] = []
    for record in records:
        if record.get("status") != "APPROVED":
            continue
        hypothesis = record.get("hypothesis") or {}
        if str(hypothesis.get("symbol", "")).upper() != symbol.upper():
            continue
        if str(hypothesis.get("timeframe", "")).upper() != timeframe.upper():
            continue
        name = str(record.get("strategy_name", ""))
        version = str(record.get("strategy_version", ""))
        rules = hypothesis.get("rules", {})
        lines.append(f"{name}:{version} rules={rules}")
    return "\n".join(lines)
