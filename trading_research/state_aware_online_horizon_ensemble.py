"""Causal state-aware online expert+horizon ensemble.

The learner keeps independent exponentially-decayed scores for each
(state, expert, horizon) arm. State is derived only from current/past prices:
trend sign from SMA20/SMA50 and coarse volatility from recent-vs-longer
absolute returns. Outcomes enter an arm only after that arm's horizon closes.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .online_expert_ensemble import EXPERTS, _direction

HORIZONS = (4, 8)

@dataclass(frozen=True)
class Prediction:
    index: int
    state: str
    expert: str
    horizon: int
    direction: str
    net_return_bps: float


def _state(closes: Sequence[float], index: int) -> str | None:
    if index < 49:
        return None
    fast = mean(closes[index - 19:index + 1])
    slow = mean(closes[index - 49:index + 1])
    trend = "UP" if fast > slow else "DOWN" if fast < slow else "FLAT"
    if index < 20:
        return None
    recent = mean(abs(closes[i] / closes[i - 1] - 1.0) for i in range(index - 7, index + 1))
    base = mean(abs(closes[i] / closes[i - 1] - 1.0) for i in range(index - 19, index + 1))
    vol = "HIGHVOL" if recent > base else "LOWVOL"
    return f"{trend}_{vol}"


def evaluate_state_aware_online_ensemble(
    bars: Sequence[Bar], *, future_bars: int = 4,
    transaction_cost_bps: float = 4.0, half_life: float = 60.0,
    min_history: int = 120, folds: int = 4,
) -> dict[str, object]:
    if future_bars <= 0 or half_life <= 0 or min_history < 0 or folds <= 0:
        raise ValueError("invalid parameters")
    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    closes = [bar.close for bar in bars]
    states = {i: _state(closes, i) for i in candidates}
    keys = [(state, expert, horizon) for state in {s for s in states.values() if s} for expert in EXPERTS for horizon in HORIZONS]
    scores = {key: 0.0 for key in keys}
    observations = {key: 0 for key in keys}
    completed = {h: 0 for h in HORIZONS}
    decay = exp(-1.0 / half_life)
    predictions: list[Prediction] = []
    fold_values: list[list[float]] = [[] for _ in range(folds)]

    for index in candidates:
        for horizon in HORIZONS:
            cutoff = index - horizon
            while completed[horizon] < len(candidates) and candidates[completed[horizon]] <= cutoff:
                j = candidates[completed[horizon]]
                completed[horizon] += 1
                state = states.get(j)
                if state is None or j + horizon >= len(bars):
                    continue
                raw = (closes[j + horizon] / closes[j] - 1.0) * 10_000.0
                for expert in EXPERTS:
                    direction = _direction(closes, j, expert)
                    if direction is None:
                        continue
                    signed = raw if direction == "LONG" else -raw
                    key = (state, expert, horizon)
                    scores[key] = decay * scores[key] + (1.0 - decay) * (signed - transaction_cost_bps)
                    observations[key] += 1

        state = states.get(index)
        if state is None or index + future_bars >= len(bars):
            continue
        eligible = [k for k in keys if k[0] == state and observations[k] >= min_history]
        if len(eligible) < 2:
            continue
        ranked = sorted(eligible, key=lambda k: scores[k], reverse=True)
        best, second = ranked[0], ranked[1]
        if scores[best] <= 0.0:
            continue
        _, expert, horizon = best
        if index + horizon >= len(bars):
            continue
        direction = _direction(closes, index, expert)
        if direction is None:
            continue
        raw = (closes[index + horizon] / closes[index] - 1.0) * 10_000.0
        signed = raw if direction == "LONG" else -raw
        net = signed - transaction_cost_bps
        fold = min(folds - 1, index * folds // len(bars))
        fold_values[fold].append(net)
        predictions.append(Prediction(index, state, expert, horizon, direction, net))

    nets = [p.net_return_bps for p in predictions]
    fold_net = [mean(v) if v else 0.0 for v in fold_values]
    return {
        "policy": "causal_state_aware_online_expert_horizon_ensemble",
        "experts": EXPERTS,
        "horizons": HORIZONS,
        "candidate_bars": len(candidates),
        "decisions": len(predictions),
        "decision_rate": len(predictions) / len(candidates) if candidates else 0.0,
        "mean_net_return_bps": mean(nets) if nets else 0.0,
        "positive_net_rate": sum(v > 0 for v in nets) / len(nets) if nets else 0.0,
        "fold_net_returns": fold_net,
        "folds_positive": sum(v > 0 for v in fold_net),
        "state_counts": {s: sum(p.state == s for p in predictions) for s in sorted({p.state for p in predictions})},
        "selected_expert_counts": {e: sum(p.expert == e for p in predictions) for e in EXPERTS},
        "selected_horizon_counts": {str(h): sum(p.horizon == h for p in predictions) for h in HORIZONS},
        "parameters": {"future_bars": future_bars, "transaction_cost_bps": transaction_cost_bps, "half_life": half_life, "min_history": min_history, "folds": folds},
        "causal_rule": "State, expert and horizon scores use only current/past information; each completed outcome enters its own state/expert/horizon arm once after its horizon completes.",
    }
