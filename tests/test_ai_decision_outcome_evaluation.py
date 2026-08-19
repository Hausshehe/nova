from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_research.ai_decision_outcome_evaluation import evaluate_ai_decision_outcomes
from trading_research.data import Bar
from trading_research.market_reasoner import MarketAnalysis


class FakeReasoner:
    def analyze(self, event, *, strategy_context="", market_context=""):
        return MarketAnalysis(
            assessment="SETUP",
            rationale="bounded test",
            relevant_strategies=(),
            urgency="ELEVATED",
            recommendation=type(
                "R",
                (),
                {"action": "ENTER", "confidence": 0.8},
            )(),
        )


def _bars(n: int = 60) -> list[Bar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(start + timedelta(days=i), 1.0, 1.0, 1.0, 1.0 + i * 0.0001, 1.0)
        for i in range(n)
    ]


def test_empty_candidates_return_zero_report() -> None:
    report = evaluate_ai_decision_outcomes([], reasoner=FakeReasoner(), sample_limit=4)
    assert report.sampled_candidate_bars == 0
    assert report.evaluated_ai_decisions == 0


def test_sample_limit_is_bounded() -> None:
    report = evaluate_ai_decision_outcomes(_bars(), reasoner=FakeReasoner(), sample_limit=2)
    assert report.sampled_candidate_bars <= 2
    assert report.evaluated_ai_decisions <= 2
