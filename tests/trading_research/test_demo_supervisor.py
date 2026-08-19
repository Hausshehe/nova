from datetime import datetime, timezone

import pytest

from trading_research.demo_supervisor import DemoTradingSupervisor, SupervisorConfig


NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def supervisor():
    return DemoTradingSupervisor(now=lambda: NOW)


def test_healthy_demo_session_passes():
    result = supervisor().check(
        market_timestamp=NOW,
        broker_connected=True,
        demo_mode=True,
        reconciled=True,
    )
    assert result.healthy is True
    assert result.reasons == ()


def test_stale_market_data_trips_kill_switch():
    s = supervisor()
    result = s.check(
        market_timestamp=NOW.replace(minute=59),
        broker_connected=True,
        demo_mode=True,
        reconciled=True,
    )
    assert result.healthy is False
    assert any(r.startswith("stale_market_data:") for r in result.reasons)
    with pytest.raises(RuntimeError, match="not healthy"):
        s.require_healthy()


def test_live_mode_is_rejected():
    s = supervisor()
    result = s.check(
        market_timestamp=NOW,
        broker_connected=True,
        demo_mode=False,
        reconciled=True,
    )
    assert result.healthy is False
    assert "demo_mode_required" in result.reasons


def test_disconnect_or_reconciliation_failure_is_rejected():
    result = supervisor().check(
        market_timestamp=NOW,
        broker_connected=False,
        demo_mode=True,
        reconciled=False,
    )
    assert result.healthy is False
    assert "broker_disconnected" in result.reasons
    assert "account_not_reconciled" in result.reasons


def test_future_market_timestamp_is_rejected():
    result = supervisor().check(
        market_timestamp=NOW.replace(hour=13),
        broker_connected=True,
        demo_mode=True,
        reconciled=True,
    )
    assert result.healthy is False
    assert "market_data_timestamp_in_future" in result.reasons


def test_custom_staleness_threshold():
    s = DemoTradingSupervisor(
        config=SupervisorConfig(max_market_data_age_seconds=5),
        now=lambda: NOW,
    )
    result = s.check(
        market_timestamp=NOW.replace(second=NOW.second - 6),
        broker_connected=True,
        demo_mode=True,
        reconciled=True,
    )
    assert result.healthy is False
