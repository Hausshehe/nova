import json
from pathlib import Path

from trading_research.market_monitor import MarketMonitor, MarketSnapshot
from trading_research.data import Bar
from trading_research.escalation import AdaptiveEscalator


def test_escalation_audit_components_produce_deterministic_classification():
    monitor = MarketMonitor()
    escalator = AdaptiveEscalator()
    bars = [
        Bar("2026-01-01T00:00:00+00:00", 1.0, 1.001, 0.999, 1.0, 100),
        Bar("2026-01-02T00:00:00+00:00", 1.0, 1.025, 1.0, 1.024, 100),
    ]

    events = []
    for bar in bars:
        events.extend(monitor.observe(MarketSnapshot("EURUSD", "1D", bar)))

    decisions = [escalator.evaluate(event) for event in events]
    assert events
    assert any(decision.request_ai for decision in decisions)
    assert all(decision.recommended_poll_seconds > 0 for decision in decisions)


def test_audit_output_schema_is_json_serializable(tmp_path):
    payload = {
        "schema_version": 1,
        "bars": 2,
        "events": 3,
        "ai_requests": 1,
        "ai_request_rate": 1 / 3,
    }
    output = tmp_path / "audit.json"
    output.write_text(json.dumps(payload), encoding="utf-8")
    assert json.loads(output.read_text(encoding="utf-8"))["ai_requests"] == 1
