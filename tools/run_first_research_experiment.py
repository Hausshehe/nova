"""Run Nova's first pre-registered market research experiment.

This is a thin experiment definition. The deterministic execution, splitting,
gating, and standardized record are owned by ``trading_research.experiment``.

Hypothesis: a 20/50-day SMA trend-following signal on EURUSD daily bars has
positive expectancy after explicit transaction costs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.contracts import Hypothesis, ResearchGates
from trading_research.experiment import run_experiment


FAST = 20
SLOW = 50
FEE_BPS = 1.0
SLIPPAGE_BPS = 1.0


def signal(bars, index: int) -> bool:
    if index + 1 < SLOW:
        return False
    fast = sum(bar.close for bar in bars[index + 1 - FAST : index + 1]) / FAST
    slow = sum(bar.close for bar in bars[index + 1 - SLOW : index + 1]) / SLOW
    return fast > slow


def build_hypothesis(symbol: str) -> Hypothesis:
    return Hypothesis(
        name="daily_sma20_sma50_trend_following",
        thesis="A fast daily moving average above a slow daily moving average indicates persistent upward momentum.",
        symbol=symbol,
        timeframe="1D",
        rules={
            "entry": "SMA20(close) > SMA50(close), evaluated only after bar close; enter next bar open",
            "exit": "SMA20(close) <= SMA50(close), evaluated only after bar close; exit next bar open",
            "costs": "1 bps fee + 1 bps slippage per side",
        },
        expected_edge="Positive expectancy after stated transaction costs on unseen data.",
        falsifier="Held-out test expectancy is non-positive or any initial research gate fails.",
        rationale="Pre-registered baseline chosen to test the research pipeline, not to optimize parameters.",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    record = run_experiment(
        csv_path=str(args.csv),
        hypothesis=build_hypothesis(args.symbol),
        signal=signal,
        gates=ResearchGates(),
        fee_bps=FEE_BPS,
        slippage_bps=SLIPPAGE_BPS,
    )
    payload = record.to_dict()
    payload["hypothesis"]["fast_sma"] = FAST
    payload["hypothesis"]["slow_sma"] = SLOW
    text = json.dumps(payload, indent=2, default=str)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
