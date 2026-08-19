from datetime import datetime, timedelta, timezone

from trading_research.data import Bar
from trading_research.volatility_mean_reversion import HYPOTHESIS, LOOKBACK, Z_ENTRY, desired_long_state, signal


def _bars(closes):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(days=index),
            open=value,
            high=value,
            low=value,
            close=value,
            volume=1.0,
        )
        for index, value in enumerate(closes)
    ]


def test_hypothesis_contract_is_fixed_and_valid():
    HYPOTHESIS.validate()
    assert HYPOTHESIS.rules["lookback"] == str(LOOKBACK)
    assert HYPOTHESIS.rules["entry_z"] == str(Z_ENTRY)
    assert HYPOTHESIS.rules["execution"] == "next_bar_open"


def test_signal_has_no_position_before_lookback():
    bars = _bars([100.0] * LOOKBACK)
    assert signal(bars, LOOKBACK - 2) is False


def test_deep_negative_deviation_enters_and_persists_until_mean():
    closes = [100.0] * (LOOKBACK - 1) + [90.0, 88.0, 87.0, 100.0]
    bars = _bars(closes)
    assert signal(bars, LOOKBACK) is True
    assert signal(bars, LOOKBACK + 1) is True
    assert signal(bars, LOOKBACK + 2) is False


def test_signal_is_causal_against_future_appends():
    prefix = [100.0] * (LOOKBACK - 1) + [90.0, 88.0, 87.0]
    bars = _bars(prefix)
    full = _bars(prefix + [150.0, 150.0, 150.0])

    for index in range(LOOKBACK - 1, len(prefix)):
        assert signal(bars, index) == signal(full, index)
        assert desired_long_state(bars, index) == desired_long_state(full, index)
