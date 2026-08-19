from datetime import datetime, timezone

from trading_research.adaptive_market_brain import AdaptiveMarketBrain
from trading_research.demo_orchestrator import DemoTradingOrchestrator
from trading_research.demo_supervisor import DemoTradingSupervisor
from trading_research.execution import DemoExecutionGateway
from trading_research.escalation import AdaptiveEscalator
from trading_research.data import Bar
from trading_research.market_monitor import MarketMonitor
from trading_research.memory import ExperienceStore
from trading_research.replay import HistoricalReplay


class FakeReasoner:
    def __init__(self):
        self.calls = 0

    def analyze(self, event, *, strategy_context="", market_context=""):
        from trading_research.market_reasoner import MarketAnalysis

        self.calls += 1
        return MarketAnalysis(
            assessment="WATCH",
            rationale="Replay event inspected.",
            relevant_strategies=(),
            urgency="ELEVATED",
        )


def bars():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    values = [1.1000, 1.1001, 1.1025, 1.1026]
    return tuple(
        Bar(
            timestamp=base.replace(day=1 + index),
            open=value,
            high=value + 0.0005,
            low=value - 0.0005,
            close=value,
            volume=1000,
        )
        for index, value in enumerate(values)
    )


def orchestrator(tmp_path, reasoner):
    experience = ExperienceStore(tmp_path / "experience.sqlite3")
    brain = AdaptiveMarketBrain(AdaptiveEscalator(), reasoner)
    return DemoTradingOrchestrator(
        brain=brain,
        supervisor=DemoTradingSupervisor(now=lambda: bars()[-1].timestamp),
        experience=experience,
        gateway=DemoExecutionGateway(),
        strategy_lookup=lambda *_: False,
        strategy_version_resolver=lambda *_: None,
    )


def test_replay_is_deterministic_and_does_not_execute_without_trade_recommendation(tmp_path):
    reasoner = FakeReasoner()
    replay = HistoricalReplay(MarketMonitor(), orchestrator(tmp_path, reasoner))
    summary, results = replay.run("EURUSD", "1D", bars())

    assert summary.bars == 4
    assert summary.events > 0
    assert summary.ai_reviews >= 1
    assert summary.executions == 0
    assert reasoner.calls == summary.ai_reviews
    assert all(result.execution is None for result in results)


def test_replay_rejects_mismatched_spread_history(tmp_path):
    reasoner = FakeReasoner()
    replay = HistoricalReplay(MarketMonitor(), orchestrator(tmp_path, reasoner))
    try:
        replay.run("EURUSD", "1D", bars(), spread_bps=[1.0])
    except ValueError as exc:
        assert "match bars length" in str(exc)
    else:
        raise AssertionError("expected ValueError")
