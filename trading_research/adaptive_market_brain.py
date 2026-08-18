"""Bridge between deterministic market escalation and optional AI reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .escalation import AdaptiveEscalator, EscalationDecision
from .market_monitor import MarketEvent
from .market_reasoner import GroqMarketReasoner, MarketAnalysis


@dataclass(frozen=True)
class AdaptiveMarketResult:
    escalation: EscalationDecision
    analysis: MarketAnalysis | None


class AdaptiveMarketBrain:
    """Use Python for continuous observation and Groq only for escalated events."""

    def __init__(
        self,
        escalator: AdaptiveEscalator,
        reasoner: GroqMarketReasoner | None = None,
        strategy_context_provider: Callable[[MarketEvent], str] | None = None,
    ) -> None:
        self.escalator = escalator
        self.reasoner = reasoner
        self.strategy_context_provider = strategy_context_provider

    def process(self, event: MarketEvent, *, market_context: str = "") -> AdaptiveMarketResult:
        decision = self.escalator.evaluate(event)
        if not decision.request_ai or self.reasoner is None:
            return AdaptiveMarketResult(decision, None)

        strategy_context = (
            self.strategy_context_provider(event)
            if self.strategy_context_provider is not None
            else ""
        )
        analysis = self.reasoner.analyze(
            event,
            market_context=market_context,
            strategy_context=strategy_context,
        )
        return AdaptiveMarketResult(decision, analysis)


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
