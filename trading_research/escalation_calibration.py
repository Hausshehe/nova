"""Calibrate escalation aggressiveness against opportunity recall."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .data import Bar
from .escalation import AdaptiveEscalator
from .opportunity_recall import evaluate_opportunity_recall, OpportunityRecallReport


@dataclass(frozen=True)
class EscalationCalibrationPoint:
    opportunity_move_bps: float
    recall: float
    ai_requests: int
    missed_opportunities: int


def calibrate(
    bars: Sequence[Bar],
    *,
    thresholds_bps: Sequence[float] = (10.0, 20.0, 30.0, 40.0, 60.0),
) -> tuple[EscalationCalibrationPoint, ...]:
    """Measure recall across opportunity definitions without changing policy."""
    points: list[EscalationCalibrationPoint] = []
    for threshold in thresholds_bps:
        report: OpportunityRecallReport = evaluate_opportunity_recall(
            bars,
            opportunity_move_bps=threshold,
            escalator=AdaptiveEscalator(),
        )
        points.append(
            EscalationCalibrationPoint(
                opportunity_move_bps=threshold,
                recall=report.recall,
                ai_requests=report.ai_requests,
                missed_opportunities=report.missed_opportunities,
            )
        )
    return tuple(points)
