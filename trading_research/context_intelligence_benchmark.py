"""Bounded causal benchmark for price-only versus richer market context.

This benchmark asks a narrow question: does causal information from related markets
improve a price-only decision process? It deliberately does not call an LLM or search
strategies. We first prove that extra information has value; only then do we expose
that validated information to Nova's language-model reasoning layer.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
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
MIN_COVERAGE_RATIO = 0.70


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


def _volatility(closes: Sequence[float], index: int, period: int = 20) -> float:
    if index < period + 1:
        return 0.0
    returns = [closes[j] / closes[j - 1] - 1.0 for j in range(index - period + 1, index + 1)]
    if not returns:
        return 0.0
    m = mean(returns)
    return mean((value - m) ** 2 for value in returns) ** 0.5


def _expert_scores(history: Sequence[tuple[int, float]], closes: Sequence[float]) -> dict[str, float]:
    scores = {expert: [] for expert in EXPERTS}
    for idx, raw_future_bps in history[-TRAIN_MIN:]:
        for expert in EXPERTS:
            direction = _direction(closes, idx, expert)
            if direction is None:
                continue
            signed = raw_future_bps if direction == "LONG" else -raw_future_bps
            scores[expert].append(signed - TRANSACTION_COST_BPS)
    return {
        expert: mean(values) if values else float("-inf")
        for expert, values in scores.items()
    }


def _context_signature(series: dict[str, Sequence[Bar]], focal: str, index: int) -> tuple[str, str]:
    focal_bars = series[focal]
    focal_prev = focal_bars[index - 20].close
    focal_ret = focal_bars[index].close / focal_prev - 1.0 if focal_prev > 0 else 0.0

    cross_returns: list[float] = []
    for bars in series.values():
        previous = bars[index - 20].close
        if previous > 0:
            cross_returns.append(bars[index].close / previous - 1.0)
    median_cross = sorted(cross_returns)[len(cross_returns) // 2]
    relative = "strong" if focal_ret > median_cross else "weak"

    closes = [bar.close for bar in focal_bars]
    volatility = "high_vol" if _volatility(closes, index) >= 0.008 else "normal_vol"
    return relative, volatility


def _load() -> dict[str, Sequence[Bar]]:
    raw: dict[str, Sequence[Bar]] = {}
    for instrument in INSTRUMENTS:
        path = DATA_DIR / f"{instrument}_{TIMEFRAME}.csv"
        if not path.exists():
            raise FileNotFoundError(path)
        raw[instrument] = load_csv(path)

    # Different instruments can legitimately have different bar counts. Align by
    # exact timestamp instead of assuming positional alignment.
    common = set.intersection(*(set(bar.timestamp for bar in bars) for bars in raw.values()))
    if len(common) < TRAIN_MIN + FUTURE_BARS + 100:
        raise ValueError(f"insufficient_common_timestamps:{len(common)}")
    timestamps = sorted(common)
    aligned: dict[str, Sequence[Bar]] = {}
    for instrument, bars in raw.items():
        by_time = {bar.timestamp: bar for bar in bars}
        aligned[instrument] = tuple(by_time[timestamp] for timestamp in timestamps)
    return aligned


def _evaluate_asset(series: dict[str, Sequence[Bar]], focal: str) -> tuple[float, float, int, int, list[FoldResult], bool]:
    bars = series[focal]
    closes = [bar.close for bar in bars]
    start = max(TRAIN_MIN + 50, 100)

    # Precompute realized four-bar outcomes, but only release each outcome to the
    # learner once its horizon has completed. This is the key causal constraint.
    realized = {
        index: (closes[index + FUTURE_BARS] / closes[index] - 1.0) * 10_000.0
        for index in range(start, len(bars) - FUTURE_BARS)
    }

    history: list[tuple[int, float]] = []
    baseline: list[Decision] = []
    contextual: list[Decision] = []
    folds: list[list[float]] = [[] for _ in range(TEST_FOLDS)]
    fold_context: list[list[float]] = [[] for _ in range(TEST_FOLDS)]

    for index in range(start, len(bars) - FUTURE_BARS):
        # At decision index i, outcome i-4 has just completed. Older outcomes are
        # already known. Outcome i itself is NOT available yet.
        completed_index = index - FUTURE_BARS
        if completed_index in realized:
            history.append((completed_index, realized[completed_index]))

        if len(history) < TRAIN_MIN:
            continue

        fold = min(TEST_FOLDS - 1, index * TEST_FOLDS // len(bars))
        raw_bps = realized[index]

        price_scores = _expert_scores(history, closes)
        best_price = max(EXPERTS, key=lambda expert: price_scores[expert])
        price_direction = _direction(closes, index, best_price)
        if price_direction is not None:
            signed = raw_bps if price_direction == "LONG" else -raw_bps
            net = signed - TRANSACTION_COST_BPS
            baseline.append(Decision(index, price_direction, net))
            folds[fold].append(net)

        signature = _context_signature(series, focal, index)
        context_scores: dict[str, list[float]] = {expert: [] for expert in EXPERTS}
        for hist_index, hist_raw in history[-TRAIN_MIN:]:
            if _context_signature(series, focal, hist_index) != signature:
                continue
            for expert in EXPERTS:
                direction = _direction(closes, hist_index, expert)
                if direction is None:
                    continue
                signed = hist_raw if direction == "LONG" else -hist_raw
                context_scores[expert].append(signed - TRANSACTION_COST_BPS)

        usable_context = {
            expert: mean(values)
            for expert, values in context_scores.items()
            if values
        }
        if usable_context:
            best_context = max(usable_context, key=usable_context.get)
            context_direction = _direction(closes, index, best_context)
            if context_direction is not None:
                signed = raw_bps if context_direction == "LONG" else -raw_bps
                net = signed - TRANSACTION_COST_BPS
                contextual.append(Decision(index, context_direction, net))
                fold_context[fold].append(net)

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

    baseline_mean = mean([x.net_bps for x in baseline]) if baseline else 0.0
    context_mean = mean([x.net_bps for x in contextual]) if contextual else 0.0
    coverage = len(contextual) / len(baseline) if baseline else 0.0
    positive_folds = sum(
        fold.context_mean_net_bps > fold.baseline_mean_net_bps
        for fold in fold_results
    )
    pass_asset = (
        context_mean > baseline_mean
        and positive_folds >= 3
        and coverage >= MIN_COVERAGE_RATIO
    )
    return baseline_mean, context_mean, len(baseline), len(contextual), fold_results, pass_asset


def run() -> dict[str, object]:
    series = _load()
    assets: dict[str, object] = {}
    asset_passes = []

    for focal in ("NAS100", "XAGUSD"):
        baseline, context, baseline_n, context_n, folds, asset_pass = _evaluate_asset(series, focal)
        asset_passes.append(asset_pass)
        assets[focal] = {
            "baseline_mean_net_bps": baseline,
            "context_mean_net_bps": context,
            "incremental_net_bps": context - baseline,
            "baseline_decisions": baseline_n,
            "context_decisions": context_n,
            "coverage_ratio": context_n / baseline_n if baseline_n else 0.0,
            "asset_pass": asset_pass,
            "folds": [asdict(item) for item in folds],
        }

    overall = "PASS" if all(asset_passes) else "MIXED" if any(asset_passes) else "FAIL"
    summary = {
        "status": overall,
        "price_only": "fixed online expert selection using focal-market history",
        "context_enriched": "same fixed experts selected using causal relative-strength and volatility regime context across six markets",
        "causal": True,
        "future_bars": FUTURE_BARS,
        "transaction_cost_bps": TRANSACTION_COST_BPS,
        "min_train_history": TRAIN_MIN,
        "min_context_coverage_ratio": MIN_COVERAGE_RATIO,
        "assets": assets,
        "interpretation_rule": {
            "PASS": "context beats baseline overall, beats it on at least 3 of 4 chronological folds, and retains at least 70% of baseline decisions on both target assets",
            "MIXED": "context helps one target asset but not both",
            "FAIL": "no target asset satisfies the preregistered context improvement gate",
        },
        "important_limit": "This is an information-value benchmark, not a claim that an LLM or news feed has been validated. The next phase only exists if this gate passes or yields a narrowly reproducible mixed result.",
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    run()
