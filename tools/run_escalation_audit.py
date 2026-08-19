"""Audit Nova's adaptive escalation against historical market data.

No Groq calls are made. The audit measures exactly which deterministic market
monitor events would request AI reasoning, grouped by event type and urgency.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_research.data import load_csv
from trading_research.escalation import AdaptiveEscalator
from trading_research.market_monitor import MarketMonitor, MarketSnapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--output", default="research/experiments/escalation_audit_001.json")
    args = parser.parse_args()

    bars = load_csv(Path(args.csv))
    monitor = MarketMonitor()
    escalator = AdaptiveEscalator()
    event_counts: Counter[str] = Counter()
    escalation_counts: Counter[str] = Counter()
    poll_counts: Counter[int] = Counter()

    for bar in bars:
        events = monitor.observe(
            MarketSnapshot(symbol="EURUSD", timeframe="1D", bar=bar)
        )
        for event in events:
            event_counts[event.event_type] += 1
            decision = escalator.evaluate(event)
            escalation_counts["AI" if decision.request_ai else "ROUTINE"] += 1
            poll_counts[decision.recommended_poll_seconds] += 1

    total_events = sum(event_counts.values())
    ai_requests = escalation_counts["AI"]
    payload = {
        "schema_version": 1,
        "dataset": args.csv,
        "bars": len(bars),
        "events": total_events,
        "ai_requests": ai_requests,
        "ai_request_rate": (ai_requests / total_events) if total_events else 0.0,
        "event_types": dict(event_counts),
        "escalation_classes": dict(escalation_counts),
        "recommended_poll_seconds": {str(k): v for k, v in sorted(poll_counts.items())},
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
