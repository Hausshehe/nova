from datetime import datetime, timedelta, timezone

from trading_research.adaptive_opportunity_policy import build_walk_forward_policy
from trading_research.data import Bar


def _bars(n=80):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(Bar(base + timedelta(days=i), 1.0 + i * 0.0001, 1.0 + i * 0.0001, 1.0 + i * 0.0001, 1.0 + i * 0.0001, 1) for i in range(n))


def test_policy_is_causal():
    bars = _bars()
    decisions = build_walk_forward_policy(bars, min_samples=2)
    assert len(decisions) == len(bars)
    assert decisions[0].request_ai is False


def test_policy_thresholds_validate():
    try:
        build_walk_forward_policy([], min_confidence=0)
    except ValueError as exc:
        assert "min_confidence" in str(exc)
    else:
        raise AssertionError("expected ValueError")
