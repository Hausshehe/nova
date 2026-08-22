from datetime import datetime, timedelta, timezone

from trading_research.broader_campaign_runner import mean_reversion_signal_series
from trading_research.data import Bar


def _bars(count: int = 30):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(hours=4 * i),
            open=100.0 + i * 0.1,
            high=101.0 + i * 0.1,
            low=99.0 + i * 0.1,
            close=100.0 + i * 0.1,
            volume=1.0,
        )
        for i in range(count)
    ]


def test_mean_reversion_signal_does_not_use_current_bar():
    original = _bars()
    mutated = list(original)
    mutated[25] = Bar(
        timestamp=original[25].timestamp,
        open=100.0,
        high=250.0,
        low=50.0,
        close=250.0,
        volume=1.0,
    )

    original_states = mean_reversion_signal_series(original)
    mutated_states = mean_reversion_signal_series(mutated)

    assert original_states[25] == mutated_states[25]


def test_mean_reversion_requires_prior_completed_window():
    states = mean_reversion_signal_series(_bars(20))
    assert states == [False] * 20
