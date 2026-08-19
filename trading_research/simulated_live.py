"""Deterministic simulated-live runner for the trading research pipeline.

This layer deliberately stops at the demo/simulation boundary. It does not
connect to MT5, place live orders, or require an LLM. A caller supplies an
observation callback so tests can model when deeper reasoning would occur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence


@dataclass(frozen=True)
class SimulatedBar:
    timestamp: str
    close: float


@dataclass
class SimulationMetrics:
    bars: int = 0
    review_requests: int = 0
    actions: int = 0
    rejected_actions: int = 0
    pnl: float = 0.0
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def record_equity(self, equity: float) -> None:
        self.peak_equity = max(self.peak_equity, equity)
        if self.peak_equity > 0:
            self.max_drawdown = max(
                self.max_drawdown,
                (self.peak_equity - equity) / self.peak_equity,
            )


@dataclass(frozen=True)
class SimulationDecision:
    review: bool
    action: str = "HOLD"
    reason: str = ""


DecisionFn = Callable[[Sequence[SimulatedBar]], SimulationDecision]


def run_simulation(
    bars: Iterable[SimulatedBar],
    decide: DecisionFn,
    *,
    initial_equity: float = 1.0,
) -> SimulationMetrics:
    """Replay bars deterministically and measure the decision pipeline.

    The callback represents the already-validated reasoning/policy boundary;
    this function never executes broker operations.
    """
    metrics = SimulationMetrics()
    history: list[SimulatedBar] = []
    equity = initial_equity
    metrics.peak_equity = initial_equity

    for bar in bars:
        history.append(bar)
        metrics.bars += 1
        decision = decide(tuple(history))

        if decision.review:
            metrics.review_requests += 1
        if decision.action == "REJECT":
            metrics.rejected_actions += 1
            if decision.reason:
                metrics.reasons.append(decision.reason)
            continue
        if decision.action in {"BUY", "SELL", "EXIT"}:
            metrics.actions += 1

        metrics.record_equity(equity)

    metrics.pnl = equity - initial_equity
    return metrics
