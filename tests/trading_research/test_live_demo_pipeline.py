from datetime import datetime, timezone

from trading_research.adaptive_market_brain import AdaptiveMarketBrain
from trading_research.data import Bar
from trading_research.demo_orchestrator import DemoTradingOrchestrator
from trading_research.demo_supervisor import DemoTradingSupervisor
from trading_research.decision_contract import AIRecommendation
from trading_research.escalation import AdaptiveEscalator
from trading_research.execution import DemoExecutionGateway
from trading_research.live_demo_pipeline import LiveDemoPipeline
from trading_research.market_history import MarketHistoryStore
from trading_research.market_monitor import MarketMonitor, MarketSnapshot
from trading_research.market_reasoner import MarketAnalysis
from trading_research.memory import ExperienceStore


NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


class FakeReasoner:
    def __init__(self, recommendation=None):
        self.calls = 0
        self.recommendation = recommendation

    def analyze(self, event, *, strategy_context="", market_context=""):
        self.calls += 1
        return MarketAnalysis(
            assessment="RISK" if self.recommendation else "WATCH",
            rationale="integration review",
            relevant_strategies=((self.recommendation.strategy_name,) if self.recommendation else ()),
            urgency="CRITICAL" if self.recommendation else "ELEVATED",
            recommendation=self.recommendation,
        )


def snapshot(close, *, previous=None):
    bar = Bar(
        timestamp=NOW,
        open=close,
        high=close + 0.0005,
        low=close - 0.0005,
        close=close,
        volume=1000,
    )
    return MarketSnapshot(
        symbol="EURUSD",
        timeframe="15M",
        bar=bar,
        previous_bar=previous,
        spread_bps=2.0,
    )


def build_pipeline(tmp_path, reasoner, approved=True):
    experience = ExperienceStore(tmp_path / "experience.sqlite3")
    gateway = DemoExecutionGateway()
    brain = AdaptiveMarketBrain(AdaptiveEscalator(), reasoner)
    orchestrator = DemoTradingOrchestrator(
        brain=brain,
        supervisor=DemoTradingSupervisor(now=lambda: NOW),
        experience=experience,
        gateway=gateway,
        strategy_lookup=(lambda name, version: approved and (name, version) == ("approved_v1", "1.0")),
        strategy_version_resolver=lambda *_: "1.0",
    )
    history = MarketHistoryStore(tmp_path / "market.sqlite3")
    pipeline = LiveDemoPipeline(
        monitor=MarketMonitor(),
        history=history,
        orchestrator=orchestrator,
    )
    return pipeline, gateway, history


def test_pipeline_persists_snapshot_and_keeps_routine_event_out_of_groq(tmp_path):
    reasoner = FakeReasoner()
    pipeline, gateway, history = build_pipeline(tmp_path, reasoner)

    result = pipeline.process_snapshot(snapshot(1.1000))

    assert result.events
    assert reasoner.calls == 0
    assert gateway.records == ()
    assert len(history.recent("EURUSD", "15M", 10)) == 1


def test_pipeline_escalates_meaningful_move_to_reasoner_but_watch_does_not_execute(tmp_path):
    reasoner = FakeReasoner()
    pipeline, gateway, history = build_pipeline(tmp_path, reasoner)

    first = snapshot(1.1000)
    pipeline.process_snapshot(first)
    second_bar = Bar(
        timestamp=NOW.replace(minute=15),
        open=1.1000,
        high=1.1030,
        low=1.1000,
        close=1.1030,
        volume=1000,
    )
    result = pipeline.process_snapshot(
        MarketSnapshot("EURUSD", "15M", second_bar, previous_bar=first.bar, spread_bps=2.0)
    )

    assert result.events
    assert reasoner.calls >= 1
    assert gateway.records == ()
    assert len(history.recent("EURUSD", "15M", 10)) == 2


def test_pipeline_allows_only_approved_structured_exit_in_demo(tmp_path):
    recommendation = AIRecommendation(
        action="EXIT",
        strategy_name="approved_v1",
        strategy_version="1.0",
        rationale="validated exit",
        urgency="CRITICAL",
        confidence=0.9,
    )
    reasoner = FakeReasoner(recommendation)
    pipeline, gateway, _ = build_pipeline(tmp_path, reasoner, approved=True)

    pipeline.process_snapshot(snapshot(1.1000))
    second_bar = Bar(
        timestamp=NOW.replace(minute=15),
        open=1.1000,
        high=1.1030,
        low=1.1000,
        close=1.1030,
        volume=1000,
    )
    result = pipeline.process_snapshot(
        MarketSnapshot("EURUSD", "15M", second_bar, previous_bar=None, spread_bps=2.0)
    )

    assert reasoner.calls >= 1
    assert result.cycles
    assert gateway.records
    assert gateway.records[-1].recommendation.strategy_version == "1.0"


def test_pipeline_rejects_unapproved_structured_exit(tmp_path):
    recommendation = AIRecommendation(
        action="EXIT",
        strategy_name="approved_v1",
        strategy_version="1.0",
        rationale="validated exit",
        urgency="CRITICAL",
        confidence=0.9,
    )
    reasoner = FakeReasoner(recommendation)
    pipeline, gateway, _ = build_pipeline(tmp_path, reasoner, approved=False)

    pipeline.process_snapshot(snapshot(1.1000))
    second_bar = Bar(
        timestamp=NOW.replace(minute=15),
        open=1.1000,
        high=1.1030,
        low=1.1000,
        close=1.1030,
        volume=1000,
    )
    result = pipeline.process_snapshot(
        MarketSnapshot("EURUSD", "15M", second_bar, spread_bps=2.0)
    )

    assert result.cycles
    assert any(c.policy_reason == "strategy_not_approved" for c in result.cycles)
    assert gateway.records == ()
