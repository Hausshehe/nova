from __future__ import annotations

from collections import Counter
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices

EXPERTS = ("sma", "mom4", "mom8", "mom12", "contrarian4", "contrarian8", "long_only", "short_only")


def _direction(closes: Sequence[float], i: int, expert: str) -> str | None:
    def momentum(h: int) -> str | None:
        if i < h:
            return None
        move = closes[i] / closes[i-h] - 1.0
        return "LONG" if move > 0 else "SHORT" if move < 0 else None
    if expert == "sma":
        if i < 49:
            return None
        fast = sum(closes[i-19:i+1]) / 20.0
        slow = sum(closes[i-49:i+1]) / 50.0
        return "LONG" if fast > slow else "SHORT" if fast < slow else None
    if expert == "mom4": return momentum(4)
    if expert == "mom8": return momentum(8)
    if expert == "mom12": return momentum(12)
    if expert == "contrarian4":
        d = momentum(4); return None if d is None else ("SHORT" if d == "LONG" else "LONG")
    if expert == "contrarian8":
        d = momentum(8); return None if d is None else ("SHORT" if d == "LONG" else "LONG")
    if expert == "long_only": return "LONG"
    if expert == "short_only": return "SHORT"
    raise ValueError(expert)


def evaluate_consensus_coverage(bars: Sequence[Bar], *, folds: int = 4) -> dict[str, object]:
    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    closes = [b.close for b in bars]
    counts = Counter()
    fold_counts = [Counter() for _ in range(folds)]
    for i in candidates:
        votes = [d for e in EXPERTS if (d := _direction(closes, i, e)) is not None]
        if not votes:
            continue
        long_votes = votes.count("LONG")
        short_votes = votes.count("SHORT")
        agreement = max(long_votes, short_votes)
        counts[agreement] += 1
        fold = min(folds - 1, i * folds // len(bars))
        fold_counts[fold][agreement] += 1
    return {
        "policy": "causal_consensus_coverage_diagnostic",
        "candidate_bars": len(candidates),
        "agreement_histogram": {str(k): counts[k] for k in sorted(counts)},
        "fold_agreement_histograms": [dict(sorted(c.items())) for c in fold_counts],
        "experts": EXPERTS,
        "causal_rule": "Consensus uses only current/past prices; no future outcomes are used in agreement measurement.",
    }
