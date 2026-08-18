"""Small, deterministic contracts for evidence-first trading research.

The research loop is intentionally explicit:

    hypothesis -> rules -> backtest -> evaluation -> gate decision

No component in this module decides that a strategy is profitable. It only
records evidence and applies predefined gates so weak ideas can be rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class Decision(str, Enum):
    REJECT = "REJECT"
    PROMISING = "PROMISING"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class Hypothesis:
    """A falsifiable market hypothesis.

    ``rules`` must be explicit enough that a deterministic backtester can run
    them without asking the language model what the rule meant.
    """

    name: str
    thesis: str
    symbol: str
    timeframe: str
    rules: Mapping[str, str]
    expected_edge: str
    falsifier: str
    rationale: str = ""

    def validate(self) -> None:
        errors: list[str] = []
        if not self.name.strip():
            errors.append("name is required")
        if not self.thesis.strip():
            errors.append("thesis is required")
        if not self.symbol.strip():
            errors.append("symbol is required")
        if not self.timeframe.strip():
            errors.append("timeframe is required")
        if not self.rules:
            errors.append("rules are required")
        if not self.expected_edge.strip():
            errors.append("expected_edge is required")
        if not self.falsifier.strip():
            errors.append("falsifier is required")
        if errors:
            raise ValueError("Invalid hypothesis: " + "; ".join(errors))


@dataclass(frozen=True)
class BacktestMetrics:
    """Deterministic metrics used by the first research gate."""

    trades: int
    net_return: float
    max_drawdown: float
    profit_factor: float
    expectancy: float
    win_rate: float
    average_win: float
    average_loss: float

    def validate(self) -> None:
        if self.trades < 0:
            raise ValueError("trades cannot be negative")
        if not 0.0 <= self.win_rate <= 1.0:
            raise ValueError("win_rate must be between 0 and 1")
        if self.max_drawdown < 0.0:
            raise ValueError("max_drawdown cannot be negative")
        if self.profit_factor < 0.0:
            raise ValueError("profit_factor cannot be negative")


@dataclass(frozen=True)
class ResearchGates:
    """Predefined stop conditions for an evidence-first experiment.

    These are intentionally conservative defaults. They are not a promise of
    profitability and must be reviewed before any live-money use.
    """

    minimum_trades: int = 100
    minimum_profit_factor: float = 1.15
    minimum_expectancy: float = 0.0
    maximum_drawdown: float = 0.25
    minimum_win_rate: float = 0.35

    def validate(self) -> None:
        if self.minimum_trades < 1:
            raise ValueError("minimum_trades must be positive")
        if self.minimum_profit_factor <= 0.0:
            raise ValueError("minimum_profit_factor must be positive")
        if self.maximum_drawdown <= 0.0 or self.maximum_drawdown >= 1.0:
            raise ValueError("maximum_drawdown must be between 0 and 1")
        if not 0.0 <= self.minimum_win_rate <= 1.0:
            raise ValueError("minimum_win_rate must be between 0 and 1")


@dataclass(frozen=True)
class GateDecision:
    decision: Decision
    reasons: Sequence[str] = field(default_factory=tuple)


def evaluate_gate(metrics: BacktestMetrics, gates: ResearchGates) -> GateDecision:
    """Apply deterministic rejection/promotion gates to one backtest."""
    metrics.validate()
    gates.validate()

    reasons: list[str] = []
    if metrics.trades < gates.minimum_trades:
        reasons.append(f"too_few_trades:{metrics.trades}<{gates.minimum_trades}")
    if metrics.profit_factor < gates.minimum_profit_factor:
        reasons.append(
            f"profit_factor_below_gate:{metrics.profit_factor:.4f}<{gates.minimum_profit_factor:.4f}"
        )
    if metrics.expectancy <= gates.minimum_expectancy:
        reasons.append(
            f"expectancy_not_positive:{metrics.expectancy:.6f}<={gates.minimum_expectancy:.6f}"
        )
    if metrics.max_drawdown > gates.maximum_drawdown:
        reasons.append(
            f"drawdown_above_gate:{metrics.max_drawdown:.4f}>{gates.maximum_drawdown:.4f}"
        )
    if metrics.win_rate < gates.minimum_win_rate:
        reasons.append(
            f"win_rate_below_gate:{metrics.win_rate:.4f}<{gates.minimum_win_rate:.4f}"
        )

    if reasons:
        return GateDecision(Decision.REJECT, tuple(reasons))
    return GateDecision(Decision.PROMISING, ("all_initial_gates_passed",))
