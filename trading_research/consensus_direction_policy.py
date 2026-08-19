"""Causal fixed-expert consensus policy.

Experts use only current/past prices. A decision is allowed only when at least
6 of 8 fixed experts agree on direction; otherwise the system abstains.
This is research-only and never changes the high-recall candidate gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices

EXPERTS = ("sma", "mom4", "mom8", "mom12", "contrarian4", "contrarian8", "long_only", "short_only")
AGREEMENT_REQUIRED = 6

@dataclass(frozen=True)
class ConsensusResult:
    index: int
    direction: str | None
    agreement_count: int
    net_return_bps: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sma(c: Sequence[float], i: int) -> str | None:
    if i < 49: return None
    fast, slow = mean(c[i-19:i+1]), mean(c[i-49:i+1])
    if fast == slow: return None
    return "LONG" if fast > slow else "SHORT"


def _mom(c: Sequence[float], i: int, h: int) -> str | None:
    if i < h: return None
    move = c[i] / c[i-h] - 1.0
    if move == 0: return None
    return "LONG" if move > 0 else "SHORT"


def _direction(c: Sequence[float], i: int, expert: str) -> str | None:
    if expert == "sma": return _sma(c, i)
    if expert == "mom4": return _mom(c, i, 4)
    if expert == "mom8": return _mom(c, i, 8)
    if expert == "mom12": return _mom(c, i, 12)
    if expert == "contrarian4":
        d = _mom(c, i, 4); return None if d is None else ("SHORT" if d == "LONG" else "LONG")
    if expert == "contrarian8":
        d = _mom(c, i, 8); return None if d is None else ("SHORT" if d == "LONG" else "LONG")
    if expert == "long_only": return "LONG"
    if expert == "short_only": return "SHORT"
    raise ValueError(expert)


def evaluate_consensus_direction(
    bars: Sequence[Bar], *, future_bars: int = 4,
    transaction_cost_bps: float = 4.0, folds: int = 4,
) -> dict[str, object]:
    if future_bars <= 0 or folds <= 0: raise ValueError("invalid parameters")
    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    closes = [b.close for b in bars]
    results: list[ConsensusResult] = []
    fold_values: list[list[float]] = [[] for _ in range(folds)]
    for i in candidates:
        votes = [_direction(closes, i, e) for e in EXPERTS]
        long_votes = sum(v == "LONG" for v in votes)
        short_votes = sum(v == "SHORT" for v in votes)
        if max(long_votes, short_votes) < AGREEMENT_REQUIRED or i + future_bars >= len(bars):
            results.append(ConsensusResult(i, None, max(long_votes, short_votes), None))
            continue
        direction = "LONG" if long_votes > short_votes else "SHORT"
        raw = (closes[i + future_bars] / closes[i] - 1.0) * 10_000.0
        signed = raw if direction == "LONG" else -raw
        net = signed - transaction_cost_bps
        fold = min(folds - 1, i * folds // len(bars))
        fold_values[fold].append(net)
        results.append(ConsensusResult(i, direction, max(long_votes, short_votes), net))
    trades = [r for r in results if r.direction is not None]
    nets = [r.net_return_bps for r in trades if r.net_return_bps is not None]
    fold_net = [mean(v) if v else 0.0 for v in fold_values]
    return {
        "policy": "causal_fixed_expert_consensus",
        "candidate_bars": len(candidates),
        "decisions": len(trades),
        "decision_rate": len(trades) / len(candidates) if candidates else 0.0,
        "mean_net_return_bps": mean(nets) if nets else 0.0,
        "positive_net_rate": sum(v > 0 for v in nets) / len(nets) if nets else 0.0,
        "fold_net_returns": fold_net,
        "folds_positive": sum(v > 0 for v in fold_net),
        "agreement_required": AGREEMENT_REQUIRED,
        "experts": EXPERTS,
        "causal_rule": "Direction uses current/past prices only; future close movement is evaluation-only.",
    }
