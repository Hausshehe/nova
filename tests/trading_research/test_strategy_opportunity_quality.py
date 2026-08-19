from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.strategy_opportunity_quality import evaluate_strategy_opportunities


def _bar(i: int, close: float) -> Bar:
    ts = datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
    return Bar(ts, close, close, close, close, 1.0)


def test_strategy_opportunity_quality_is_cost_aware_and_diagnostic():
    bars = [_bar(i, 1.0) for i in range(55)]
    bars += [_bar(55, 1.004), _bar(56, 1.006), _bar(57, 1.008), _bar(58, 1.010)]
    report = evaluate_strategy_opportunities(bars, future_bars=4, opportunity_move_bps=30.0, transaction_cost_bps_round_trip=4.0)
    assert report.opportunities >= 1
    assert report.transaction_cost_bps == 4.0
    assert 0 <= report.actionable_opportunities <= report.opportunities
    assert 0.0 <= report.actionable_recall <= 1.0
    assert report.recalls_with_ai_review <= report.actionable_opportunities
