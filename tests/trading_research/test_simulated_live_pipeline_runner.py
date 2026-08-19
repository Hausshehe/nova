from datetime import datetime, timezone

from trading_research.adaptive_market_brain import AdaptiveMarketBrain
from trading_research.data import Bar
from trading_research.demo_orchestrator import DemoTradingOrchestrator
from trading_research.demo_supervisor import DemoTradingSupervisor
from trading_research.escalation import AdaptiveEscalator
from trading_research.execution import DemoExecutionGateway
from trading_research.live_demo_pipeline import LiveDemoPipeline
from trading_research.market_history import MarketHistoryStore
from trading_research.market_monitor import MarketMonitor, MarketSnapshot
from trading_research.memory import ExperienceStore
from trading_research.market_reasoner import MarketAnalysis


class FakeReasoner:
    def __init__(self):
        self.calls = 0

    def analyze(self, event, *, strategy_context="", market_context=""):
        self.calls += 1
        return MarketAnalysis(
            assessment="WATCH",
            rationale="architecture-only review",
            relevant_strategies=(),
            urgency="ELEVATED",
        )


def test_historical_bars_run_through_real_pipeline_without_execution():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [
        Bar(base, 1.1000, 1.1005, 1.0995, 1.1000, 1000),
        Bar(base.replace(day=2), 1.1000, 1.1035, 1.1000, 1.1030, 1000),
        Bar(base.replace(day=3), 1.1030, 1.1035, 1.1025, 1.1031, 1000),
    ]
    reasoner = FakeReasoner()
    gateway = DemoExecutionGateway()
    history = MarketHistoryStore(":memory:")
    orchestrator = DemoTradingOrchestrator(
        brain=AdaptiveMarketBrain(AdaptiveEscalator(), reasoner),
        supervisor=DemoTradingSupervisor(now=lambda: bars[-1].timestamp),
        experience=ExperienceStore(":memory:"),
        gateway=gateway,
        strategy_lookup=lambda *_: False,
        strategy_version_resolver=lambda *_: None,
    )
    pipeline = LiveDemoPipeline(
        monitor=MarketMonitor(),
        history=history,
        orchestrator=orchestrator,
    )

    results = []
    for bar in bars:
        results.append(pipeline.process_snapshot(MarketSnapshot("EURUSD", "1D", bar)))

    assert len(history.recent("EURUSD", "1D", 10)) == 3
    assert any(result.events for result in results)
    assert reasoner.calls >= 1
    assert gateway.records == ()
