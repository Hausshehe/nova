from trading_research.simulated_live import (
    SimulatedBar,
    SimulationDecision,
    run_simulation,
)


def test_simulation_replays_all_bars_and_counts_reviews_without_broker():
    bars = [
        SimulatedBar("2026-01-01T08:00:00Z", 1.0),
        SimulatedBar("2026-01-01T08:01:00Z", 1.1),
        SimulatedBar("2026-01-01T08:02:00Z", 1.2),
    ]

    def decide(history):
        return SimulationDecision(review=len(history) == 2, action="HOLD")

    result = run_simulation(bars, decide)

    assert result.bars == 3
    assert result.review_requests == 1
    assert result.actions == 0
    assert result.rejected_actions == 0
    assert result.pnl == 0.0


def test_rejected_decisions_are_measured_and_reason_recorded():
    bars = [SimulatedBar("2026-01-01T08:00:00Z", 1.0)]

    result = run_simulation(
        bars,
        lambda history: SimulationDecision(
            review=True,
            action="REJECT",
            reason="stale_market_data",
        ),
    )

    assert result.review_requests == 1
    assert result.rejected_actions == 1
    assert result.actions == 0
    assert result.reasons == ["stale_market_data"]
