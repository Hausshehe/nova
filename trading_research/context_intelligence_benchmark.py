"""Bounded causal benchmark for price-only versus richer market context.

This module tests whether information from related markets adds predictive value to a
price-only baseline. It does not search a strategy space, tune a prompt, or call an LLM.
That separation is intentional: first prove information value, then add language-model
reasoning on top of a validated context representation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean
from typing import Sequence

from .data import Bar, load_csv
from .online_expert_ensemble import EXPERTS, _direction

DATA_DIR = Path("data/research/universe_v2")
RESULT_PATH = Path("data/research/context_intelligence_benchmark.json")
INSTRUMENTS = ("NAS100", "US500", "US30", "XAUUSD", "XAGUSD", "WTI")
TIMEFRAME = "4H"
FUTURE_BARS = 4
TRANSACTION_COST_BPS = 4.0
TRAIN_MIN = 120
TEST_FOLDS = 4


@dataclass(frozen=True)
class Decision:
    index: int
    direction: str
    net_bps: float


@dataclass(frozen=True)
class FoldResult:
    fold: int
    baseline_decisions: int
    context_decisions: int
    baseline_mean_net_bps: float
    context_mean_net_bps: float
    baseline_positive_rate: float
    context_positive_rate: float


def _trend(closes: Sequence[float], index: int) -> float:
    if index < 50:
        return 0.0
    fast = mean(closes[index - 19 : index + 1])
    slow = mean(closes[index - 49 : index + 1])
    return 1.0 if fast > slow else -1.0 if fast < slow else 0.0


def _volatility(closes: Sequence[float], index: int, period: int = 20) -> float:
    if index < period + 1:
        return 0.0
    returns = [closes[j] / closes[j - 1] - 1.0 for j in range(index - period + 1, index + 1)]
    m = mean(returns)
    return (mean([(x - m) ** 2 for x in returns]) ** 0.5) if returns else 0.0


def _expert_rank_from_price(history: Sequence[tuple[int, float]], closes: Sequence[float]) -> list[str]:
    scores = {expert: 0.0 for expert in EXPERTS}
    counts = {expert: 0 for expert in EXPERTS}
    for idx, raw_future_bps in history[-TRAIN_MIN:]:
        for expert in EXPERTS:
            direction = _direction(closes, idx, expert)
            if direction is None:
                continue
            signed = raw_future_bps if direction == "LONG" else -raw_future_bps
            scores[expert] += signed - TRANSACTION_COST_BPS
            counts[expert] += 1
    return sorted(EXPERTS, key=lambda e: scores[e] / counts[e] if counts[e] else float("-inf"), reverse=True)


def _context_signature(series: dict[str, Sequence[Bar]], focal: str, index: int) -> tuple[str, str]:
    focal_close = series[focal][index].close
    focal_prev = series[focal][index - 20].close
    focal_ret = focal_close / focal_prev - 1.0 if focal_prev > 0 else 0.0
    cross = []
    for instrument, bars in series.items():
        prev = bars[index - 20].close
        if prev > 0:
            cross.append(bars[index].close / prev - 1.0)
    median_cross = sorted(cross)[len(cross) // 2] if cross else 0.0
    relative = "strong" if focal_ret > median_cross else "weak"
    vol = _volatility([bar.close for bar in series[focal]], index)
    volatility = "high_vol" if vol >= 0.008 else "normal_vol"
    return relative, volatility


def _load() -> dict[str, Sequence[Bar]]:
    series: dict[str, Sequence[Bar]] = {}
    for instrument in INSTRUMENTS:
        path = DATA_DIR / f"{instrument}_{TIMEFRAME}.csv"
        if not path.exists():
            raise FileNotFoundError(path)
        series[instrument] = load_csv(path)
    lengths = {len(bars) for bars in series.values()}
    if len(lengths) != 1:
        raise ValueError(f"unaligned_lengths:{sorted(lengths)}")
    return series


def _evaluate_asset(series: dict[str, Sequence[Bar]], focal: str) -> tuple[float, float, int, int, list[FoldResult]]:
    bars = series[focal]
    closes = [bar.close for bar in bars]
    # Build a fixed, causal history of completed outcomes. No future label is used
    # before its horizon has fully completed.
    history: list[tuple[int, float]] = []
    baseline: list[Decision] = []
    contextual: list[Decision] = []
    folds: list[list[float]] = [[] for _ in range(TEST_FOLDS)]
    fold_context: list[list[float]] = [[] for _ in range(TEST_FOLDS)]

    start = max(TRAIN_MIN + 50, 100)
    for index in range(start, len(bars) - FUTURE_BARS):
        # Evaluate the two policies using only history ending strictly before index.
        if history:
            ranked = _expert_rank_from_price(history, closes)
            best = ranked[0]
            direction = _direction(closes, index, best)
        else:
            direction = None
        raw_bps = (closes[index + FUTURE_BARS] / closes[index] - 1.0) * 10_000.0
        fold = min(TEST_FOLDS - 1, index * TEST_FOLDS // len(bars))

        if direction is not None:
            signed = raw_bps if direction == "LONG" else -raw_bps
            net = signed - TRANSACTION_COST_BPS
            baseline.append(Decision(index, direction, net))
            folds[fold].append(net)

        signature = _context_signature(series, focal, index)
        candidates = []
        # Context is used only to choose among the fixed experts. The expert set and
        # scoring rule are frozen; there is no search over indicators or thresholds.
        for expert in EXPERTS:
            scores: list[float] = []
            for hist_idx, hist_raw in history:
                if _context_signature(series, focal, hist_idx) != signature:
                    continue
                hist_direction = _direction(closes, hist_idx, expert)
                if hist_direction is None:
                    continue
                signed = hist_raw if hist_direction == "LONG" else -hist_raw
                scores.append(signed - TRANSACTION_COST_BPS)
            if scores:
                candidates.append((mean(scores), expert))
        if candidates:
            _, best_context = max(candidates)
            context_direction = _direction(closes, index, best_context)
            if context_direction is not None:
                signed = raw_bps if context_direction == "LONG" else -raw_bps
                net = signed - TRANSACTION_COST_BPS
                contextual.append(Decision(index, context_direction, net))
                fold_context[fold].append(net)

        if index >= FUTURE_BARS:
            history.append((index, raw_bps))

    fold_results = []
    for fold in range(TEST_FOLDS):
        b = folds[fold]
        c = fold_context[fold]
        fold_results.append(
            FoldResult(
                fold=fold + 1,
                baseline_decisions=len(b),
                context_decisions=len(c),
                baseline_mean_net_bps=mean(b) if b else 0.0,
                context_mean_net_bps=mean(c) if c else 0.0,
                baseline_positive_rate=sum(x > 0 for x in b) / len(b) if b else 0.0,
                context_positive_rate=sum(x > 0 for x in c) / len(c) if c else 0.0,
            )
        )
    return (
        mean([x.net_bps for x in baseline]) if baseline else 0.0,
        mean([x.net_bps for x in contextual]) if contextual else 0.0,
        len(baseline),
        len(contextual),
        fold_results,
    )


def run() -> dict[str, object]:
    series = _load()
    assets = {}
    for focal in ("NAS100", "XAGUSD"):
        baseline, context, baseline_n, context_n, folds = _evaluate_asset(series, focal)
        assets[focal] = {
            "baseline_mean_net_bps": baseline,
            "context_mean_net_bps": context,
            "incremental_net_bps": context - baseline,
            "baseline_decisions": baseline_n,
            "context_decisions": context_n,
            "folds": [asdict(item) for item in folds],
        }

    summary = {
        "status": "FEASIBILITY_BENCHMARK_COMPLETE",
        "price_only": "fixed online expert selection using focal-market history",
        "context_enriched": "same fixed experts, selected using causal related-market regime context",
        "causal": True,
        "future_bars": FUTURE_BARS,
        "transaction_cost_bps": TRANSACTION_COST_BPS,
        "assets": assets,
        "interpretation_rule": {
            "PASS": "context must improve mean net return on both target assets and on at least 3 of 4 folds for each asset, without materially collapsing decision coverage",
            "MIXED": "improvement is confined to one asset or fewer than 3 folds",
            "FAIL": "no robust incremental improvement",
        },
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    run()
