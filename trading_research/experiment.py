"""Deterministic end-to-end research experiment runner.

The runner owns the mechanical research pipeline:

    CSV -> validation -> chronological split -> hypothesis validation
        -> deterministic backtests -> gates -> standardized record

AI does not execute code or define success criteria here. A hypothesis must
arrive as a validated deterministic rule function plus an explicit contract.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from .backtest import BacktestResult, run_long_flat
from .contracts import BacktestMetrics, Decision, GateDecision, Hypothesis, ResearchGates, evaluate_gate
from .data import Bar, DatasetSplit, chronological_split, load_csv
from .memory import ExperienceStore
from .strategy_registry import Strategy, StrategyRegistry

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
    dataset_sha256: str
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


def _dataset_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _sync_strategy_registry(
    *,
    hypothesis: Hypothesis,
    final_decision: Decision,
    strategy_version: str,
    memory_store: ExperienceStore,
) -> None:
    """Record research state while preserving lifecycle/execution authority."""
    registry = StrategyRegistry(memory_store)
    existing = memory_store.get_strategy(hypothesis.name, strategy_version)

    if existing is None:
        registry.register(
            Strategy(
                name=hypothesis.name,
                version=strategy_version,
                status="CANDIDATE",
                research_state=final_decision.value,
                hypothesis={
                    "thesis": hypothesis.thesis,
                    "symbol": hypothesis.symbol,
                    "timeframe": hypothesis.timeframe,
                    "rules": dict(hypothesis.rules),
                    "expected_edge": hypothesis.expected_edge,
                    "falsifier": hypothesis.falsifier,
                    "rationale": hypothesis.rationale,
                },
                notes=f"automatic research result: {final_decision.value}",
            )
        )
        return

    # Research runs may update evidence for CANDIDATE strategies only. Existing
    # APPROVED/RETIRED/BLOCKED lifecycle states require a separate lifecycle
    # decision and must never be silently changed by a backtest.
    if existing["status"] == "CANDIDATE":
        registry.set_research_state(
            hypothesis.name,
            strategy_version,
            final_decision.value,
            reason=f"automatic research result: {final_decision.value}",
        )


def run_experiment(
    *,
    csv_path: str,
    hypothesis: Hypothesis,
    signal: Signal,
    gates: ResearchGates | None = None,
    fee_bps: float = 1.0,
    slippage_bps: float = 1.0,
    strategy_version: str = "1.0",
    memory_store: ExperienceStore | None = None,
) -> ExperimentRecord:
    """Run one bounded, reproducible hypothesis experiment.

    When a memory store is supplied, the resulting research state is synced to
    the strategy registry. Registry updates never grant or revoke execution
    authority for already-approved strategies.
    """
    if fee_bps < 0 or slippage_bps < 0:
        raise ValueError("fee_bps and slippage_bps cannot be negative")
    if not strategy_version.strip():
        raise ValueError("strategy_version is required")

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

    if any(segment.decision.decision is Decision.REJECT for segment in segments):
        final_decision = Decision.REJECT
    elif any(segment.decision.decision is Decision.INCONCLUSIVE for segment in segments):
        final_decision = Decision.INCONCLUSIVE
    else:
        final_decision = Decision.PROMISING

    record = ExperimentRecord(
        schema_version=1,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        hypothesis=hypothesis,
        dataset=str(csv_path),
        dataset_sha256=_dataset_sha256(csv_path),
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

    if memory_store is not None:
        _sync_strategy_registry(
            hypothesis=hypothesis,
            final_decision=final_decision,
            strategy_version=strategy_version,
            memory_store=memory_store,
        )

    return record
