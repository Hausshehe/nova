from datetime import datetime, timedelta, timezone

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


def snapshot(close, *, timestamp=NOW):
    bar = Bar(timestamp, close, close + 0.0005, close - 0.0005, close, 1000)
    return MarketSnapshot("EURUSD", "15M", bar, spread_bps=2.0)


def build_pipeline(tmp_path, reasoner, approved=True):
    experience = ExperienceStore(tmp_path / "experience.sqlite3")
    gateway = DemoExecutionGateway()
    brain = AdaptiveMarketBrain(AdaptiveEscalator(), reasoner)
    clock = {"now": NOW}
    orchestrator = DemoTradingOrchestrator(
        brain=brain,
        supervisor=DemoTradingSupervisor(now=lambda: clock["now"]),
        experience=experience,
        gateway=gateway,
        strategy_lookup=lambda name, version: approved and (name, version) == ("approved_v1", "1.0"),
        strategy_version_resolver=lambda *_: "1.0",
        position_direction_resolver=lambda _: "LONG",
    )
    history = MarketHistoryStore(tmp_path / "market.sqlite3")
    return LiveDemoPipeline(monitor=MarketMonitor(), history=history, orchestrator=orchestrator), gateway, history, clock


def test_pipeline_persists_snapshot_and_keeps_routine_event_out_of_groq(tmp_path):
    reasoner = FakeReasoner()
    pipeline, gateway, history, _ = build_pipeline(tmp_path, reasoner)
    result = pipeline.process_snapshot(snapshot(1.1000))
    assert result.events
    assert reasoner.calls == 0
    assert gateway.records == ()
    assert len(history.recent("EURUSD", "15M", 10)) == 1


def test_pipeline_escalates_meaningful_move_to_reasoner_but_watch_does_not_execute(tmp_path):
    reasoner = FakeReasoner()
    pipeline, gateway, history, clock = build_pipeline(tmp_path, reasoner)
    pipeline.process_snapshot(snapshot(1.1000))
    second_time = NOW + timedelta(minutes=15)
    clock["now"] = second_time
    result = pipeline.process_snapshot(snapshot(1.1030, timestamp=second_time))
    assert result.events
    assert reasoner.calls >= 1
    assert gateway.records == ()
    assert len(history.recent("EURUSD", "15M", 10)) == 2


def test_pipeline_allows_only_approved_structured_exit_in_demo(tmp_path):
    recommendation = AIRecommendation("EXIT", "approved_v1", "1.0", "validated exit", "CRITICAL", 0.9)
    reasoner = FakeReasoner(recommendation)
    pipeline, gateway, _, clock = build_pipeline(tmp_path, reasoner, approved=True)
    pipeline.process_snapshot(snapshot(1.1000))
    second_time = NOW + timedelta(minutes=15)
    clock["now"] = second_time
    result = pipeline.process_snapshot(snapshot(1.1030, timestamp=second_time))
    assert reasoner.calls >= 1
    assert result.cycles
    assert gateway.records
    assert gateway.records[-1].recommendation.strategy_version == "1.0"


def test_pipeline_rejects_unapproved_structured_exit(tmp_path):
    recommendation = AIRecommendation("EXIT", "approved_v1", "1.0", "validated exit", "CRITICAL", 0.9)
    reasoner = FakeReasoner(recommendation)
    pipeline, gateway, _, clock = build_pipeline(tmp_path, reasoner, approved=False)
    pipeline.process_snapshot(snapshot(1.1000))
    second_time = NOW + timedelta(minutes=15)
    clock["now"] = second_time
    result = pipeline.process_snapshot(snapshot(1.1030, timestamp=second_time))
    assert result.cycles
    assert any(c.policy_reason == "strategy_not_approved" for c in result.cycles)
    assert gateway.records == ()
