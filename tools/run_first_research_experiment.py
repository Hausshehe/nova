"""Run Nova's first pre-registered market research experiment.

This is a thin experiment definition. The deterministic execution, splitting,
gating, standardized record, experience memory, and strategy research-state
sync are owned by the research layers.

Memory records evidence only. It cannot promote a strategy or authorize trading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.contracts import Hypothesis, ResearchGates
from trading_research.experiment import run_experiment
from trading_research.memory import ExperienceStore


FAST = 20
SLOW = 50
FEE_BPS = 1.0
SLIPPAGE_BPS = 1.0
STRATEGY_VERSION = "1.0"
DEFAULT_MEMORY = ROOT / "data" / "research" / "experience.sqlite3"


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


def experiment_id(record: dict, output: Path | None) -> str:
    """Return a stable ID for a named result, otherwise a content-derived ID."""
    if output is not None:
        return output.stem
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return "exp-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def persist_experiment(record, payload: dict, memory_path: Path, output: Path | None) -> str:
    """Persist one completed experiment without granting it any authority."""
    store = ExperienceStore(memory_path)
    exp_id = experiment_id(payload, output)
    store.record_experiment(
        experiment_id=exp_id,
        created_at_utc=record.created_at_utc,
        hypothesis_name=record.hypothesis.name,
        symbol=record.hypothesis.symbol,
        timeframe=record.hypothesis.timeframe,
        final_decision=record.final_decision.value,
        record=payload,
    )
    return exp_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--memory", type=Path, default=DEFAULT_MEMORY)
    args = parser.parse_args()

    memory_store = ExperienceStore(args.memory)
    record = run_experiment(
        csv_path=str(args.csv),
        hypothesis=build_hypothesis(args.symbol),
        signal=signal,
        gates=ResearchGates(),
        fee_bps=FEE_BPS,
        slippage_bps=SLIPPAGE_BPS,
        strategy_version=STRATEGY_VERSION,
        memory_store=memory_store,
    )
    payload = record.to_dict()
    payload["hypothesis"]["fast_sma"] = FAST
    payload["hypothesis"]["slow_sma"] = SLOW
    text = json.dumps(payload, indent=2, default=str)
    print(text)
    exp_id = persist_experiment(record, payload, args.memory, args.output)
    print(f"EXPERIENCE_RECORDED: {exp_id}")
    print(f"STRATEGY_REGISTRY_SYNC: {record.hypothesis.name}:{STRATEGY_VERSION} -> {record.final_decision.value}")
    print(f"EXPERIENCE_STORE: {args.memory}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
