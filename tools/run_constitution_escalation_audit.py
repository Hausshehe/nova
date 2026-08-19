"""Measure adaptive escalation under Nova's Trading Constitution."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_research.constitution_runtime import ConstitutionRuntime
from trading_research.data import load_csv
from trading_research.escalation import AdaptiveEscalator
from trading_research.market_monitor import MarketMonitor, MarketSnapshot
from trading_research.trading_constitution import TradingConstitution


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--output", default="research/experiments/constitution_escalation_audit_001.json")
    args = parser.parse_args()

    constitution = TradingConstitution()
    runtime = ConstitutionRuntime(constitution)
    monitor = MarketMonitor()
    escalator = AdaptiveEscalator()
    counts: Counter[str] = Counter()
    polls: Counter[int] = Counter()
    blocked = 0

    bars = load_csv(Path(args.csv))
    for bar in bars:
        for event in monitor.observe(
            MarketSnapshot(symbol="EURUSD", timeframe="1D", bar=bar)
        ):
            decision = escalator.evaluate(event)
            allowed = runtime.allow_review(
                event=event,
                request_ai=decision.request_ai,
                recommended_poll_seconds=decision.recommended_poll_seconds,
            )
            if not allowed.allowed:
                blocked += 1
                counts[f"BLOCKED:{allowed.reason}"] += 1
                continue
            counts["AI" if decision.request_ai else "ROUTINE"] += 1
            polls[decision.recommended_poll_seconds] += 1

    total = sum(counts.values()) + blocked
    ai = counts["AI"]
    payload = {
        "schema_version": 1,
        "dataset": args.csv,
        "constitution_version": constitution.version,
        "bars": len(bars),
        "events_evaluated": total,
        "ai_requests": ai,
        "ai_request_rate": ai / total if total else 0.0,
        "blocked_reviews": blocked,
        "classes": dict(counts),
        "recommended_poll_seconds": {str(k): v for k, v in sorted(polls.items())},
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
