"""Deterministic development research for regime-conditioned continuation.

The language model supplies a bounded ExperimentPlan. This module performs the
actual measurement without letting the model execute code, change gates, or
inspect confirmation data. Every explored variant is recorded for research
lineage, and selection uses a predeclared lower-confidence-bound rule.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from statistics import mean
from typing import Sequence

from .data import Bar
from .research_brain import ExperimentPlan


@dataclass(frozen=True)
class RegimeCandidateResult:
    candidate_id: str
    event_move_threshold_bps: int
    horizon_bars: int
    trend_lookback_bars: int
    trend_gap_threshold_bps: int
    volatility_lookback_bars: int
    volatility_percentile: float
    trend_events: int
    nontrend_events: int
    trend_mean_net_bps: float
    nontrend_mean_net_bps: float
    effect_bps: float
    effect_lower_95ci_bps: float
    status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RegimeResearchResult:
    family: str
    candidates_tested: int
    exploration_budget: int
    selected_candidate_id: str | None
    candidates: tuple[RegimeCandidateResult, ...]
    conclusion: str

    def to_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "candidates_tested": self.candidates_tested,
            "exploration_budget": self.exploration_budget,
            "selected_candidate_id": self.selected_candidate_id,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "conclusion": self.conclusion,
        }


def _close_return_bps(bars: Sequence[Bar], index: int, horizon: int = 1) -> float | None:
    if index + horizon >= len(bars):
        return None
    return (bars[index + horizon].close / bars[index].close - 1.0) * 10_000.0


def _realized_vol_bps(bars: Sequence[Bar], index: int, lookback: int) -> float | None:
    if index < lookback:
        return None
    values = [
        (bars[j].close / bars[j - 1].close - 1.0) * 10_000.0
        for j in range(index - lookback + 1, index + 1)
    ]
    if len(values) < 2:
        return None
    avg = mean(values)
    return sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def _causal_percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _classify_regime(
    bars: Sequence[Bar],
    index: int,
    *,
    trend_lookback: int,
    trend_gap_threshold_bps: int,
    volatility_lookback: int,
    volatility_percentile: float,
) -> str | None:
    if index < max(trend_lookback, volatility_lookback) + 1:
        return None
    closes = [bar.close for bar in bars]
    fast = mean(closes[index - trend_lookback + 1 : index + 1])
    slow_start = index - min(trend_lookback * 2, len(closes) - 1) + 1
    slow_window = closes[slow_start : index + 1]
    if not slow_window:
        return None
    slow = mean(slow_window)
    gap_bps = abs((fast / slow - 1.0) * 10_000.0) if slow else 0.0
    if gap_bps >= trend_gap_threshold_bps:
        return "TREND"

    current_vol = _realized_vol_bps(bars, index, volatility_lookback)
    if current_vol is None:
        return None
    prior_vols: list[float] = []
    start = max(volatility_lookback, index - volatility_lookback * 4)
    for j in range(start, index):
        value = _realized_vol_bps(bars, j, volatility_lookback)
        if value is not None:
            prior_vols.append(value)
    threshold = _causal_percentile(prior_vols, volatility_percentile)
    if threshold is not None and current_vol >= threshold:
        return "HIGH_VOL"
    return "RANGE"


def _candidate_grid(plan: ExperimentPlan) -> list[tuple[int, int, int, int, int, float]]:
    """Build a deterministic, bounded development grid around the base plan."""
    event_choices = tuple(dict.fromkeys(
        max(10, min(200, int(round(plan.event_move_threshold_bps * factor))))
        for factor in (0.8, 1.0, 1.2)
    ))
    horizon_choices = tuple(sorted({
        max(1, min(4, plan.horizon_bars - 1)),
        plan.horizon_bars,
        max(1, min(4, plan.horizon_bars + 1)),
    }))
    trend_lookbacks = tuple(sorted({
        max(8, plan.trend_lookback_bars - 5),
        plan.trend_lookback_bars,
        min(100, plan.trend_lookback_bars + 5),
    }))
    trend_thresholds = tuple(dict.fromkeys(
        max(1, min(500, int(round(plan.trend_gap_threshold_bps * factor))))
        for factor in (0.75, 1.0, 1.25)
    ))
    vol_lookbacks = tuple(sorted({
        max(8, plan.volatility_lookback_bars - 5),
        plan.volatility_lookback_bars,
        min(100, plan.volatility_lookback_bars + 5),
    }))
    vol_percentiles = tuple(dict.fromkeys(
        max(0.50, min(0.95, round(plan.volatility_percentile + delta, 2)))
        for delta in (-0.05, 0.0, 0.05)
    ))

    variants: list[tuple[int, int, int, int, int, float]] = []
    base = (
        plan.event_move_threshold_bps,
        plan.horizon_bars,
        plan.trend_lookback_bars,
        plan.trend_gap_threshold_bps,
        plan.volatility_lookback_bars,
        plan.volatility_percentile,
    )
    variants.append(base)

    for event in event_choices:
        for horizon in horizon_choices:
            for trend_lb in trend_lookbacks:
                for trend_thr in trend_thresholds:
                    for vol_lb in vol_lookbacks:
                        for vol_pct in vol_percentiles:
                            candidate = (event, horizon, trend_lb, trend_thr, vol_lb, vol_pct)
                            if candidate != base:
                                variants.append(candidate)
                            if len(variants) >= plan.exploration_budget:
                                return variants
    return variants[: plan.exploration_budget]


def _evaluate_candidate(
    bars: Sequence[Bar],
    *,
    candidate_id: str,
    params: tuple[int, int, int, int, int, float],
    min_events: int,
    transaction_cost_bps: float,
) -> RegimeCandidateResult:
    event_threshold, horizon, trend_lb, trend_thr, vol_lb, vol_pct = params
    trend_values: list[float] = []
    nontrend_values: list[float] = []

    for index in range(len(bars)):
        regime = _classify_regime(
            bars,
            index,
            trend_lookback=trend_lb,
            trend_gap_threshold_bps=trend_thr,
            volatility_lookback=vol_lb,
            volatility_percentile=vol_pct,
        )
        if regime is None or index == 0:
            continue
        prior_return = (bars[index].close / bars[index - 1].close - 1.0) * 10_000.0
        if abs(prior_return) < event_threshold:
            continue
        future_return = _close_return_bps(bars, index, horizon)
        if future_return is None:
            continue
        directional = future_return if prior_return > 0 else -future_return
        net = directional - transaction_cost_bps
        if regime == "TREND":
            trend_values.append(net)
        else:
            nontrend_values.append(net)

    trend_mean = mean(trend_values) if trend_values else 0.0
    nontrend_mean = mean(nontrend_values) if nontrend_values else 0.0
    effect = trend_mean - nontrend_mean

    if len(trend_values) < min_events or len(nontrend_values) < min_events:
        return RegimeCandidateResult(
            candidate_id=candidate_id,
            event_move_threshold_bps=event_threshold,
            horizon_bars=horizon,
            trend_lookback_bars=trend_lb,
            trend_gap_threshold_bps=trend_thr,
            volatility_lookback_bars=vol_lb,
            volatility_percentile=vol_pct,
            trend_events=len(trend_values),
            nontrend_events=len(nontrend_values),
            trend_mean_net_bps=trend_mean,
            nontrend_mean_net_bps=nontrend_mean,
            effect_bps=effect,
            effect_lower_95ci_bps=float("-inf"),
            status="INCONCLUSIVE_TOO_FEW_EVENTS",
        )

    trend_var = sum((x - trend_mean) ** 2 for x in trend_values) / max(1, len(trend_values) - 1)
    nontrend_var = sum((x - nontrend_mean) ** 2 for x in nontrend_values) / max(1, len(nontrend_values) - 1)
    se = sqrt(trend_var / len(trend_values) + nontrend_var / len(nontrend_values))
    lower = effect - 1.96 * se
    status = "PROMISING" if lower > 0.0 else "REJECT"

    return RegimeCandidateResult(
        candidate_id=candidate_id,
        event_move_threshold_bps=event_threshold,
        horizon_bars=horizon,
        trend_lookback_bars=trend_lb,
        trend_gap_threshold_bps=trend_thr,
        volatility_lookback_bars=vol_lb,
        volatility_percentile=vol_pct,
        trend_events=len(trend_values),
        nontrend_events=len(nontrend_values),
        trend_mean_net_bps=trend_mean,
        nontrend_mean_net_bps=nontrend_mean,
        effect_bps=effect,
        effect_lower_95ci_bps=lower,
        status=status,
    )


def run_development_regime_research(
    bars: Sequence[Bar],
    plan: ExperimentPlan,
    *,
    transaction_cost_bps: float = 4.0,
) -> RegimeResearchResult:
    """Explore only the development sample using a predeclared bounded grid."""
    plan.validate()
    if transaction_cost_bps < 0:
        raise ValueError("transaction_cost_bps cannot be negative")
    if len(bars) < 250:
        raise ValueError("development research requires at least 250 bars")

    candidates: list[RegimeCandidateResult] = []
    for number, params in enumerate(_candidate_grid(plan), 1):
        candidates.append(
            _evaluate_candidate(
                bars,
                candidate_id=f"regime-{number:02d}",
                params=params,
                min_events=plan.minimum_events_per_regime,
                transaction_cost_bps=transaction_cost_bps,
            )
        )

    eligible = [candidate for candidate in candidates if candidate.effect_lower_95ci_bps != float("-inf")]
    selected = max(eligible, key=lambda candidate: candidate.effect_lower_95ci_bps) if eligible else None
    if selected is None:
        conclusion = "INCONCLUSIVE_NO_CANDIDATE_WITH_MINIMUM_EVENTS"
    elif selected.effect_lower_95ci_bps > 0.0:
        conclusion = "DEVELOPMENT_CANDIDATE_SELECTED_NOT_CONFIRMED"
    else:
        conclusion = "NO_POSITIVE_DEVELOPMENT_EFFECT"

    return RegimeResearchResult(
        family=plan.family,
        candidates_tested=len(candidates),
        exploration_budget=plan.exploration_budget,
        selected_candidate_id=selected.candidate_id if selected else None,
        candidates=tuple(candidates),
        conclusion=conclusion,
    )


__all__ = [
    "RegimeCandidateResult",
    "RegimeResearchResult",
    "run_development_regime_research",
]
