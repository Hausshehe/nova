"""Independent 2026 replication of Nova's frozen context-information benchmark.

This is a one-shot replication of the earlier context-vs-price experiment.
It keeps the same fixed experts, context definition, cost assumption, and
causal online learning rule. 2010-2025 data provide the pre-2026 history;
2026 outcomes are evaluation-only until their four-bar horizon completes.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Sequence

from .data import Bar, load_csv
from .dukascopy_history import DukascopyClient, write_csv
from .online_expert_ensemble import EXPERTS, _direction

ROOT = Path("data/research/context_replication_2026")
RESULT_PATH = ROOT / "replication_summary.json"
INSTRUMENTS = ("US500", "NAS100", "US30", "XAUUSD", "XAGUSD", "WTI")
TIMEFRAME = "4H"
START = "2010-01-01T00:00:00+00:00"
END = "2026-08-20T00:00:00+00:00"
TEST_START = "2026-01-01T00:00:00+00:00"
FUTURE_BARS = 4
TRANSACTION_COST_BPS = 4.0
TRAIN_MIN = 120
MIN_COVERAGE_RATIO = 0.70

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
    return {expert: mean(values) if values else float("-inf") for expert, values in scores.items()}


def _context_signature(series: dict[str, Sequence[Bar]], focal: str, index: int) -> tuple[str, str]:
    focal = series[focal]
    focal_prev = focal[index - 20].close
    focal_ret = focal[index].close / focal_prev - 1.0 if focal_prev > 0 else 0.0
    cross_returns = []
    for bars in series.values():
        previous = bars[index - 20].close
        if previous > 0:
            cross_returns.append(bars[index].close / previous - 1.0)
    median_cross = sorted(cross_returns)[len(cross_returns) // 2]
    relative = "strong" if focal_ret > median_cross else "weak"
    closes = [bar.close for bar in focal]
    volatility = "high_vol" if _volatility(closes, index) >= 0.008 else "normal_vol"
    return relative, volatility


def _download() -> dict[str, tuple[Bar, ...]]:
    ROOT.mkdir(parents=True, exist_ok=True)
    raw: dict[str, tuple[Bar, ...]] = {}
    for instrument in INSTRUMENTS:
        path = ROOT / f"{instrument}_{TIMEFRAME}.csv"
        print(f"DOWNLOAD {instrument} {TIMEFRAME}", flush=True)
        candles = DukascopyClient().historical_prices(
            instrument=instrument,
            timeframe=TIMEFRAME,
            start_utc=START,
            end_utc=END,
            progress=lambda message: print(message, flush=True),
        )
        if len(candles) < 1000:
            raise RuntimeError(f"insufficient_bars:{instrument}:{len(candles)}")
        write_csv(candles, path)
        raw[instrument] = tuple(load_csv(path))
    common = set.intersection(*(set(bar.timestamp for bar in bars) for bars in raw.values()))
    common_ts = sorted(ts for ts in common)
    if len(common_ts) < 1000:
        raise RuntimeError(f"insufficient_common_timestamps:{len(common_ts)}")
    aligned = {}
    for instrument, bars in raw.items():
        by_time = {bar.timestamp: bar for bar in bars}
        aligned[instrument] = tuple(by_time[ts] for ts in common_ts)
    return aligned


def _evaluate_asset(series: dict[str, Sequence[Bar]], focal: str) -> dict[str, object]:
    bars = series[focal]
    closes = [bar.close for bar in bars]
    test_start_index = next(i for i, bar in enumerate(bars) if bar.timestamp.isoformat() >= TEST_START)
    start = max(TRAIN_MIN + 50, 100)
    if test_start_index <= start:
        raise RuntimeError(f"test_start_not_after_training:{focal}")

    realized = {
        i: (closes[i + FUTURE_BARS] / closes[i] - 1.0) * 10_000.0
        for i in range(start, len(bars) - FUTURE_BARS)
    }
    history = []
    baseline = []
    contextual = []
    folds_b = [[] for _ in range(4)]
    folds_c = [[] for _ in range(4)]
    test_indices = [i for i in range(test_start_index, len(bars) - FUTURE_BARS)]

    for index in range(start, len(bars) - FUTURE_BARS):
        completed_index = index - FUTURE_BARS
        if completed_index in realized:
            history.append((completed_index, realized[completed_index]))
        if index < test_start_index or len(history) < TRAIN_MIN:
            continue

        fold = min(3, (index - test_start_index) * 4 // max(1, len(test_indices)))
        raw_bps = realized[index]

        price_scores = _expert_scores(history, closes)
        best_price = max(EXPERTS, key=lambda expert: price_scores[expert])
        price_direction = _direction(closes, index, best_price)
        if price_direction is not None:
            signed = raw_bps if price_direction == "LONG" else -raw_bps
            folds_b[fold].append(signed - TRANSACTION_COST_BPS)
            baseline.append(signed - TRANSACTION_COST_BPS)

        signature = _context_signature(series, focal, index)
        context_scores = {expert: [] for expert in EXPERTS}
        for hist_index, hist_raw in history[-TRAIN_MIN:]:
            if _context_signature(series, focal, hist_index) != signature:
                continue
            for expert in EXPERTS:
                direction = _direction(closes, hist_index, expert)
                if direction is None:
                    continue
                signed = hist_raw if direction == "LONG" else -hist_raw
                context_scores[expert].append(signed - TRANSACTION_COST_BPS)
        usable = {expert: mean(values) for expert, values in context_scores.items() if values}
        if usable:
            best_context = max(usable, key=usable.get)
            context_direction = _direction(closes, index, best_context)
            if context_direction is not None:
                signed = raw_bps if context_direction == "LONG" else -raw_bps
                folds_c[fold].append(signed - TRANSACTION_COST_BPS)
                contextual.append(signed - TRANSACTION_COST_BPS)

    fold_results = []
    for fold in range(4):
        b, c = folds_b[fold], folds_c[fold]
        fold_results.append(FoldResult(
            fold=fold + 1,
            baseline_decisions=len(b),
            context_decisions=len(c),
            baseline_mean_net_bps=mean(b) if b else 0.0,
            context_mean_net_bps=mean(c) if c else 0.0,
            baseline_positive_rate=sum(x > 0 for x in b) / len(b) if b else 0.0,
            context_positive_rate=sum(x > 0 for x in c) / len(c) if c else 0.0,
        ))
    baseline_mean = mean(baseline) if baseline else 0.0
    context_mean = mean(contextual) if contextual else 0.0
    coverage = len(contextual) / len(baseline) if baseline else 0.0
    positive_folds = sum(r.context_mean_net_bps > r.baseline_mean_net_bps for r in fold_results)
    return {
        "baseline_mean_net_bps": baseline_mean,
        "context_mean_net_bps": context_mean,
        "incremental_net_bps": context_mean - baseline_mean,
        "baseline_decisions": len(baseline),
        "context_decisions": len(contextual),
        "coverage_ratio": coverage,
        "positive_folds": positive_folds,
        "folds": [asdict(r) for r in fold_results],
        "asset_pass": context_mean > baseline_mean and positive_folds >= 3 and coverage >= MIN_COVERAGE_RATIO,
    }


def run() -> dict[str, object]:
    series = _download()
    xag = _evaluate_asset(series, "XAGUSD")
    summary = {
        "status": "PASS" if xag["asset_pass"] else "FAIL",
        "asset": "XAGUSD",
        "test_start": TEST_START,
        "test_end": END,
        "price_only": "same fixed online expert selection as prior benchmark",
        "context_enriched": "same fixed relative-strength + volatility regime context as prior benchmark",
        "causal": True,
        "future_bars": FUTURE_BARS,
        "transaction_cost_bps": TRANSACTION_COST_BPS,
        "min_train_history": TRAIN_MIN,
        "min_context_coverage_ratio": MIN_COVERAGE_RATIO,
        "result": xag,
        "kill_rule": "A failed replication ends this context direction; no additional indicators, prompt tuning, or extra search is permitted before reclassification.",
    }
    RESULT_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return summary


if __name__ == "__main__":
    run()
