from datetime import datetime, timezone

from trading_research.data import Bar
from trading_research.strategy_escalation import build_strategy_escalation_hints


def test_hints_are_causal_and_validate_thresholds() -> None:
    bars = []
    for i in range(55):
        close = 1.0 + i * 0.0001
        bars.append(Bar(datetime(2026, 1, 1 + i, tzinfo=timezone.utc), close, close, close, close, 1))

    hints = build_strategy_escalation_hints(bars, momentum_bps=0.5, max_sma_gap_bps=35.0)
    assert len(hints) == len(bars)
    assert hints[0].request_ai is False
    assert hints[-1].index == 54
    assert hints[-1].momentum_bps > 0


def test_invalid_periods_rejected() -> None:
    try:
        build_strategy_escalation_hints([], fast_period=20, slow_period=20)
    except ValueError as exc:
        assert "slow_period" in str(exc)
    else:
        raise AssertionError("expected ValueError")
