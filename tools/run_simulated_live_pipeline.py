"""Run Nova's real demo pipeline against historical OHLCV data."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ``python tools/run_simulated_live_pipeline.py`` puts ``tools/`` on sys.path.
# Add the repository root explicitly so the runner works without PYTHONPATH.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_research.adaptive_market_brain import AdaptiveMarketBrain
from trading_research.data import load_csv
from trading_research.demo_orchestrator import DemoTradingOrchestrator
from trading_research.demo_supervisor import DemoTradingSupervisor
from trading_research.escalation import AdaptiveEscalator
from trading_research.execution import DemoExecutionGateway
from trading_research.live_demo_pipeline import LiveDemoPipeline
from trading_research.market_history import MarketHistoryStore
from trading_research.memory import ExperienceStore
from trading_research.market_monitor import MarketMonitor, MarketSnapshot
from trading_research.market_reasoner import MarketAnalysis


class ReplayReasoner:
    """Deterministic advisory reasoner for architecture validation without Groq."""

    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, event, *, strategy_context="", market_context=""):
        self.calls += 1
        return MarketAnalysis(
            assessment="WATCH",
            rationale="Simulated-live architecture review; no trade recommendation.",
            relevant_strategies=(),
            urgency="ELEVATED",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--output", default="research/experiments/simulated_live_result.json")
    args = parser.parse_args()

    bars = load_csv(Path(args.csv))
    reasoner = ReplayReasoner()
    experience = ExperienceStore(":memory:")
    history = MarketHistoryStore(":memory:")
    gateway = DemoExecutionGateway()
    brain = AdaptiveMarketBrain(AdaptiveEscalator(), reasoner)
    orchestrator = DemoTradingOrchestrator(
        brain=brain,
        supervisor=DemoTradingSupervisor(now=lambda: bars[-1].timestamp),
        experience=experience,
        gateway=gateway,
        strategy_lookup=lambda *_: False,
        strategy_version_resolver=lambda *_: None,
    )
    pipeline = LiveDemoPipeline(
        monitor=MarketMonitor(),
        history=history,
        orchestrator=orchestrator,
    )

    events = 0
    for bar in bars:
        result = pipeline.process_snapshot(
            MarketSnapshot(
                symbol="EURUSD",
                timeframe="1D",
                bar=bar,
            )
        )
        events += len(result.events)

    payload = {
        "schema_version": 1,
        "dataset": args.csv,
        "bars": len(bars),
        "events": events,
        "groq_reviews": reasoner.calls,
        "demo_executions": len(gateway.records),
        "result": "PASS" if bars and not gateway.records else "REVIEW",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
