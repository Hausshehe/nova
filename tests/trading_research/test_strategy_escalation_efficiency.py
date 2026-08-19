from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.strategy_escalation_efficiency import evaluate_strategy_escalation_efficiency


def _bar(i: int, close: float) -> Bar:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i)
    return Bar(ts, close, close, close, close, 1.0)


def test_strategy_escalation_efficiency_is_bounded() -> None:
    bars = tuple(_bar(i, 1.0 + i * 0.00001) for i in range(80))
    report = evaluate_strategy_escalation_efficiency(bars)
    assert report.ai_requests >= report.unique_ai_request_bars
    assert report.actionable_reviewed <= report.actionable_opportunities
    assert 0.0 <= report.actionable_recall <= 1.0
    assert 0.0 <= report.opportunity_precision <= 1.0
    assert report.unnecessary_ai_requests <= report.unique_ai_request_bars
