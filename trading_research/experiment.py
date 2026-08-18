"""Deterministic end-to-end research experiment runner.

The runner owns the mechanical research pipeline:

    CSV -> validation -> chronological split -> hypothesis validation
        -> deterministic backtests -> gates -> standardized record

AI does not execute code or define success criteria here. A hypothesis must
arrive as a validated deterministic rule function plus an explicit contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from .backtest import BacktestResult, run_long_flat
from .contracts import BacktestMetrics, Decision, GateDecision, Hypothesis, ResearchGates, evaluate_gate
from .data import Bar, DatasetSplit, chronological_split, load_csv

Signal = Callable[[Sequence[Bar], int], bool]


@dataclass(frozen=True)
class SegmentRecord:
    name: str
    bars: int
    start: str
    end: str
    metrics: BacktestMetrics
    decision: GateDecision


@dataclass(frozen=True)
class ExperimentRecord:
    schema_version: int
    created_at_utc: str
    hypothesis: Hypothesis
    dataset: str
    total_bars: int
    split_sizes: dict[str, int]
    costs: dict[str, float]
    segments: tuple[SegmentRecord, ...]
    final_decision: Decision

    def to_dict(self) -> dict:
        """Serialize the complete record without double-converting nested dataclasses."""
        payload = asdict(self)
        payload["hypothesis"]["rules"] = dict(sorted(self.hypothesis.rules.items()))
        for segment in payload["segments"]:
            segment["decision"]["decision"] = segment["decision"]["decision"].value
        payload["final_decision"] = self.final_decision.value
        return payload


def _metrics(result: BacktestResult) -> BacktestMetrics:
    return BacktestMetrics(
        trades=len(result.trades),
        net_return=result.final_return,
        max_drawdown=result.max_drawdown,
        profit_factor=result.profit_factor,
        expectancy=result.expectancy,
        win_rate=result.win_rate,
        average_win=result.average_win,
        average_loss=result.average_loss,
    )


def _segment_record(
    name: str,
    bars: Sequence[Bar],
    signal: Signal,
    gates: ResearchGates,
    *,
    fee_bps: float,
    slippage_bps: float,
) -> SegmentRecord:
    result = run_long_flat(
        bars,
        signal,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )
    metrics = _metrics(result)
    return SegmentRecord(
        name=name,
        bars=len(bars),
        start=bars[0].timestamp.isoformat(),
        end=bars[-1].timestamp.isoformat(),
        metrics=metrics,
        decision=evaluate_gate(metrics, gates),
    )


def run_experiment(
    *,
    csv_path: str,
    hypothesis: Hypothesis,
    signal: Signal,
    gates: ResearchGates | None = None,
    fee_bps: float = 1.0,
    slippage_bps: float = 1.0,
) -> ExperimentRecord:
    """Run one bounded, reproducible hypothesis experiment."""
    if fee_bps < 0 or slippage_bps < 0:
        raise ValueError("fee_bps and slippage_bps cannot be negative")

    hypothesis.validate()
    active_gates = gates or ResearchGates()
    active_gates.validate()

    bars = load_csv(csv_path)
    split: DatasetSplit = chronological_split(bars)
    segments = tuple(
        _segment_record(
            name,
            segment,
            signal,
            active_gates,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
        for name, segment in (
            ("train", split.train),
            ("validation", split.validation),
            ("test", split.test),
        )
    )

    # Promotion is deliberately strict: every segment must pass. Any actual
    # performance failure rejects; otherwise an insufficient sample remains
    # inconclusive and cannot be promoted.
    if any(segment.decision.decision is Decision.REJECT for segment in segments):
        final_decision = Decision.REJECT
    elif any(segment.decision.decision is Decision.INCONCLUSIVE for segment in segments):
        final_decision = Decision.INCONCLUSIVE
    else:
        final_decision = Decision.PROMISING

    return ExperimentRecord(
        schema_version=1,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        hypothesis=hypothesis,
        dataset=str(csv_path),
        total_bars=len(bars),
        split_sizes={
            "train": len(split.train),
            "validation": len(split.validation),
            "test": len(split.test),
        },
        costs={"fee_bps_per_side": fee_bps, "slippage_bps_per_side": slippage_bps},
        segments=segments,
        final_decision=final_decision,
    )
