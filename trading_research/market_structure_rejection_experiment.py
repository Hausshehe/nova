"""Frozen market-structure rejection experiment.

Hypothesis: a confirmed swing level followed by a rejection candle can predict
short-horizon direction better than chance after costs.

The rule is intentionally fixed before evaluation. No parameter search, tuning,
LLM reasoning, news, or contextual selector is used.
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Sequence

from .data import Bar, load_csv
from .dukascopy_history import DukascopyClient, write_csv

ASSETS = ("NAS100", "XAGUSD")
TIMEFRAME = "4H"
START_UTC = "2010-01-01T00:00:00+00:00"
DEV_END_UTC = "2026-01-01T00:00:00+00:00"
TEST_END_UTC = "2026-08-21T00:00:00+00:00"
FUTURE_BARS = 4
FEE_BPS = 1.0
SLIPPAGE_BPS = 1.0
MIN_TRADES = 30
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_BLOCK = 5
BOOTSTRAP_SEED = 42
PIVOT_LEFT = 2
PIVOT_RIGHT = 2
ATR_PERIOD = 20
LEVEL_TOL_ATR = 0.50
MIN_WICK_BODY_RATIO = 1.50

RAW_DIR = Path("data/research/market_structure_rejection")
RESULT_PATH = RAW_DIR / "summary.json"


@dataclass(frozen=True)
class Trade:
    index: int
    direction: str
    net_bps: float


def _atr(bars: Sequence[Bar], index: int) -> float:
    if index < ATR_PERIOD:
        return 0.0
    values = []
    for i in range(index - ATR_PERIOD + 1, index + 1):
        prev = bars[i - 1].close
        values.append(max(bars[i].high - bars[i].low, abs(bars[i].high - prev), abs(bars[i].low - prev)))
    return mean(values)


def _confirmed_pivots(bars: Sequence[Bar], index: int) -> tuple[float | None, float | None]:
    """Return latest confirmed swing high/low strictly before current bar."""
    latest_high = None
    latest_low = None
    candidate_end = index - PIVOT_RIGHT
    if candidate_end <= PIVOT_LEFT:
        return None, None
    for pivot in range(PIVOT_LEFT, candidate_end + 1):
        left = bars[pivot - PIVOT_LEFT : pivot]
        right = bars[pivot + 1 : pivot + PIVOT_RIGHT + 1]
        if len(left) < PIVOT_LEFT or len(right) < PIVOT_RIGHT:
            continue
        if all(bars[pivot].high > bar.high for bar in left) and all(bars[pivot].high >= bar.high for bar in right):
            latest_high = bars[pivot].high
        if all(bars[pivot].low < bar.low for bar in left) and all(bars[pivot].low <= bar.low for bar in right):
            latest_low = bars[pivot].low
    return latest_high, latest_low


def _signal(bars: Sequence[Bar], index: int) -> str | None:
    if index < ATR_PERIOD + PIVOT_LEFT + PIVOT_RIGHT + 1:
        return None
    atr = _atr(bars, index)
    if atr <= 0:
        return None
    swing_high, swing_low = _confirmed_pivots(bars, index)
    bar = bars[index]
    body = abs(bar.close - bar.open)
    if body <= 0:
        return None
    lower_wick = min(bar.open, bar.close) - bar.low
    upper_wick = bar.high - max(bar.open, bar.close)
    near_support = swing_low is not None and abs(bar.low - swing_low) <= LEVEL_TOL_ATR * atr
    near_resistance = swing_high is not None and abs(bar.high - swing_high) <= LEVEL_TOL_ATR * atr
    bullish_rejection = (
        near_support
        and bar.close > bar.open
        and lower_wick >= MIN_WICK_BODY_RATIO * body
        and bar.close >= bar.low + 0.60 * (bar.high - bar.low)
    )
    bearish_rejection = (
        near_resistance
        and bar.close < bar.open
        and upper_wick >= MIN_WICK_BODY_RATIO * body
        and bar.close <= bar.high - 0.60 * (bar.high - bar.low)
    )
    if bullish_rejection and not bearish_rejection:
        return "LONG"
    if bearish_rejection and not bullish_rejection:
        return "SHORT"
    return None


def _bootstrap_ci(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(values)
    block = min(BOOTSTRAP_BLOCK, n)
    starts = list(range(max(1, n - block + 1)))
    means: list[float] = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.choice(starts)
            sample.extend(values[start : start + block])
        means.append(mean(sample[:n]))
    means.sort()
    return means[int(0.025 * BOOTSTRAP_SAMPLES)], means[int(0.975 * BOOTSTRAP_SAMPLES) - 1]


def evaluate(bars: Sequence[Bar]) -> dict[str, object]:
    trades: list[Trade] = []
    last_trade_index = -10**9
    for index in range(ATR_PERIOD + PIVOT_LEFT + PIVOT_RIGHT + 1, len(bars) - FUTURE_BARS):
        direction = _signal(bars, index)
        if direction is None or index <= last_trade_index:
            continue
        raw = (bars[index + FUTURE_BARS].close / bars[index].close - 1.0) * 10_000.0
        signed = raw if direction == "LONG" else -raw
        net = signed - FEE_BPS - SLIPPAGE_BPS
        trades.append(Trade(index, direction, net))
        last_trade_index = index
    returns = [trade.net_bps for trade in trades]
    low, high = _bootstrap_ci(returns)
    mean_net = mean(returns) if returns else 0.0
    status = "PASS" if len(trades) >= MIN_TRADES and mean_net > 0 and low > 0 else "FAIL"
    return {
        "bars": len(bars),
        "trades": len(trades),
        "mean_net_bps": mean_net,
        "positive_trade_rate": sum(x > 0 for x in returns) / len(returns) if returns else 0.0,
        "bootstrap_low": low,
        "bootstrap_high": high,
        "status": status,
        "long_trades": sum(t.direction == "LONG" for t in trades),
        "short_trades": sum(t.direction == "SHORT" for t in trades),
    }


def _download(instrument: str, end_utc: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{instrument}_{TIMEFRAME}_{end_utc[:10]}.csv"
    candles = DukascopyClient().historical_prices(
        instrument=instrument,
        timeframe=TIMEFRAME,
        start_utc=START_UTC,
        end_utc=end_utc,
        progress=lambda msg: print(msg, flush=True),
    )
    if len(candles) < 500:
        raise RuntimeError(f"insufficient_bars:{instrument}:{len(candles)}")
    write_csv(candles, path)
    return path


def run() -> dict[str, object]:
    results: dict[str, object] = {}
    for asset in ASSETS:
        dev_path = _download(asset, DEV_END_UTC)
        test_path = _download(asset, TEST_END_UTC)
        dev = evaluate(load_csv(dev_path))
        test = evaluate(load_csv(test_path))
        results[asset] = {"development_2010_2025": dev, "test_2026": test}
    summary = {
        "hypothesis": "confirmed_swing_level_rejection_candle",
        "rule": {
            "pivot_left": PIVOT_LEFT,
            "pivot_right": PIVOT_RIGHT,
            "atr_period": ATR_PERIOD,
            "level_tolerance_atr": LEVEL_TOL_ATR,
            "min_wick_body_ratio": MIN_WICK_BODY_RATIO,
            "future_bars": FUTURE_BARS,
            "fee_bps_per_side": FEE_BPS,
            "slippage_bps_per_side": SLIPPAGE_BPS,
        },
        "results": results,
        "decision_rule": "Advance only if the fixed rule is positive with bootstrap lower bound > 0 on 2026 and has at least 30 trades on each asset.",
        "kill_rule": "If the 2026 test fails, do not tune this rule or add rescue filters; record it as failed and move to a different hypothesis.",
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return summary


if __name__ == "__main__":
    run()
