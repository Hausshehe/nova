from datetime import datetime, timedelta, timezone

from trading_research.intraday_replay import ReplayObservation, run_intraday_schedule


def test_intraday_schedule_counts_15_second_slots_without_sleeping():
    start = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    rows = [
        ReplayObservation(start, 1.0),
        ReplayObservation(start + timedelta(seconds=15), 1.001),
        ReplayObservation(start + timedelta(seconds=30), 1.002),
    ]
    result = run_intraday_schedule(rows, poll_seconds=15)
    assert result.observations == 3
    assert result.review_slots == 3
    assert result.elapsed_seconds == 30.0


def test_intraday_schedule_rejects_naive_timestamps():
    rows = [ReplayObservation(datetime(2026, 1, 1, 8, 0), 1.0)]
    try:
        run_intraday_schedule(rows)
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("expected ValueError")
