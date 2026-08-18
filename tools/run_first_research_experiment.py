"""Run Nova's first pre-registered market research experiment.

Hypothesis: a 20/50-day SMA trend-following signal on EURUSD daily bars has
positive expectancy after explicit transaction costs.

Entry: after a completed bar, if SMA20 > SMA50, enter long at the next open.
Exit: after a completed bar, if SMA20 <= SMA50, exit at the next open.
Falsifier: non-positive out-of-sample expectancy, or failure of the initial
research gates on the held-out test split.

This is a baseline experiment, not a claimed trading strategy. Parameters are
fixed here before seeing the result; there is no optimization loop.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_research.backtest import run_long_flat
from trading_research.contracts import BacktestMetrics, Hypothesis, ResearchGates, evaluate_gate
from trading_research.data import chronological_split, load_csv


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


def metrics(result) -> BacktestMetrics:
    return BacktestMetrics(
        trades=len(result.trades),
        net_return=result.final_return,
        max_drawdown=result.max_drawdown,
        profit_factor=result.profit_factor,
        expectancy=result.expectancy,
        win_rate=result.win_rate,
        average_win=result.average_win,
        average_loss=result.average_loss,
    )


def run(path: Path, symbol: str) -> dict:
    bars = load_csv(path)
    split = chronological_split(bars)
    hypothesis = Hypothesis(
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
    hypothesis.validate()

    gates = ResearchGates()
    results = {}
    for name, segment in (("train", split.train), ("validation", split.validation), ("test", split.test)):
        result = run_long_flat(segment, signal, fee_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS)
        m = metrics(result)
        decision = evaluate_gate(m, gates)
        results[name] = {
            "bars": len(segment),
            "trades": m.trades,
            "net_return": m.net_return,
            "max_drawdown": m.max_drawdown,
            "profit_factor": m.profit_factor,
            "expectancy": m.expectancy,
            "win_rate": m.win_rate,
            "decision": decision.decision.value,
            "reasons": list(decision.reasons),
        }

    results["hypothesis"] = {
        "name": hypothesis.name,
        "symbol": hypothesis.symbol,
        "timeframe": hypothesis.timeframe,
        "fast_sma": FAST,
        "slow_sma": SLOW,
        "fee_bps_per_side": FEE_BPS,
        "slippage_bps_per_side": SLIPPAGE_BPS,
    }
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run(args.csv, args.symbol)
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
