from datetime import datetime, time, timedelta, timezone

from trading_research.live_demo_session import DemoSessionConfig, LiveDemoSession


def test_session_polls_at_configured_interval_and_stops_at_max_polls():
    current = [datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)]
    sleeps = []
    snapshots = []
    processed = []

    def clock():
        return current[0]

    def sleep(seconds):
        sleeps.append(seconds)
        current[0] += timedelta(seconds=seconds)

    session = LiveDemoSession(
        config=DemoSessionConfig(start=time(8), end=time(16), poll_interval=timedelta(seconds=15)),
        snapshot_provider=lambda: snapshots.append("snapshot") or 1,
        event_processor=lambda value: processed.append(value) or "ok",
        sleep=sleep,
    )
    stats = session.run(now=clock, max_polls=3)

    assert stats.polls == 3
    assert stats.processed_events == 3
    assert stats.stop_reason == "max_polls"
    assert sleeps == [15.0, 15.0]
    assert snapshots == ["snapshot"] * 3
    assert processed == [1, 1, 1]


def test_session_does_not_run_outside_window():
    now = datetime(2026, 8, 18, 17, 0, tzinfo=timezone.utc)
    calls = []
    session = LiveDemoSession(
        config=DemoSessionConfig(start=time(8), end=time(16)),
        snapshot_provider=lambda: calls.append("snapshot"),
        event_processor=lambda value: calls.append(value),
        sleep=lambda _: calls.append("sleep"),
    )
    stats = session.run(now=lambda: now, max_polls=2)

    assert stats.polls == 0
    assert stats.processed_events == 0
    assert stats.stop_reason == "session_end"
    assert calls == []


def test_stop_request_prevents_next_poll():
    calls = []
    now = datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)
    session = LiveDemoSession(
        snapshot_provider=lambda: calls.append("snapshot"),
        event_processor=lambda value: calls.append(value),
        sleep=lambda _: calls.append("sleep"),
    )
    stats = session.run(now=lambda: now, max_polls=2, stop_requested=lambda: True)

    assert stats.polls == 0
    assert stats.stop_reason == "stop_requested"
    assert calls == []
