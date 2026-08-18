from datetime import datetime, time, timezone

from trading_research.adaptive_market_brain import AdaptiveMarketBrain
from trading_research.escalation import AdaptiveEscalator
from trading_research.market_monitor import EventThresholds, MarketMonitor, MarketSnapshot
from trading_research.monitor_session import MarketMonitorSession, MonitoringWindow
from trading_research.data import Bar


class FakeReasoner:
    def __init__(self):
        self.calls = []

    def analyze(self, event, *, market_context="", strategy_context=""):
        self.calls.append(event)
        return {"event": event.event_type}


def bar(ts, close):
    return Bar(ts, close - 0.001, close + 0.001, close - 0.002, close, 100.0)


def test_window_supports_overnight_schedule():
    window = MonitoringWindow(time(8), time(4))
    assert window.contains(time(8))
    assert window.contains(time(23))
    assert window.contains(time(3, 59))
    assert not window.contains(time(4))
    assert not window.contains(time(7, 59))


def test_session_routes_events_and_uses_recommended_poll():
    ts = datetime(2026, 8, 19, 10, tzinfo=timezone.utc)
    snapshots = iter([
        [MarketSnapshot("EURUSD", "1M", bar(ts, 1.1000))],
        [MarketSnapshot("EURUSD", "1M", bar(ts.replace(minute=1), 1.1030))],
    ])
    sleeps = []
    brain = AdaptiveMarketBrain(AdaptiveEscalator())
    session = MarketMonitorSession(
        MarketMonitor(EventThresholds(price_move_bps=10)),
        brain,
        lambda: next(snapshots),
        window=MonitoringWindow(time(8), time(16)),
        clock=lambda: ts,
        sleeper=sleeps.append,
    )
    ticks = session.run(max_iterations=2)
    assert len(ticks) == 2
    assert any(event.event_type == "PRICE_MOVE" for event in ticks[1].events)
    assert sleeps[-1] == 5.0


def test_session_does_not_poll_provider_outside_window():
    calls = []
    session = MarketMonitorSession(
        MarketMonitor(),
        AdaptiveMarketBrain(AdaptiveEscalator()),
        lambda: calls.append(1) or (),
        window=MonitoringWindow(time(8), time(16)),
        clock=lambda: datetime(2026, 8, 19, 7, tzinfo=timezone.utc),
        sleeper=lambda _: None,
    )
    session.run(max_iterations=2)
    assert calls == []
