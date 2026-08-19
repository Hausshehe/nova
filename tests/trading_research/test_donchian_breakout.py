from datetime import datetime, timedelta, timezone

import pytest

from trading_research.data import Bar
from trading_research.donchian_breakout import HYPOTHESIS, LOOKBACK_ENTRY, DonchianSignal


def _bars(closes, highs=None, lows=None):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    highs = highs or closes
    lows = lows or closes
    return [
        Bar(
            timestamp=start + timedelta(days=index),
            open=value,
            high=highs[index],
            low=lows[index],
            close=value,
            volume=1.0,
        )
        for index, value in enumerate(closes)
    ]


def test_hypothesis_contract_is_fixed_and_valid():
    HYPOTHESIS.validate()
    assert HYPOTHESIS.rules["entry"] == "close > maximum high of previous 55 completed bars"
    assert HYPOTHESIS.rules["exit"] == "close < minimum low of previous 20 completed bars"
    assert HYPOTHESIS.rules["execution"] == "next-bar-open"


def test_signal_enters_only_after_55_completed_bars():
    closes = [100.0] * LOOKBACK_ENTRY + [101.0]
    bars = _bars(closes)
    signal = DonchianSignal()

    assert signal(bars, LOOKBACK_ENTRY - 1) is False
    assert signal(bars, LOOKBACK_ENTRY) is True


def test_signal_exits_below_prior_20_bar_low():
    closes = [100.0] * LOOKBACK_ENTRY + [101.0] * 5 + [99.0]
    bars = _bars(closes)
    signal = DonchianSignal()

    states = [signal(bars, index) for index in range(len(bars))]
    assert states[LOOKBACK_ENTRY] is True
    assert states[-1] is False


def test_signal_resets_for_new_sequence_and_rejects_time_reversal():
    bars = _bars([100.0] * (LOOKBACK_ENTRY + 1))
    signal = DonchianSignal()
    signal(bars, LOOKBACK_ENTRY)

    with pytest.raises(ValueError, match="chronologically"):
        signal(bars, LOOKBACK_ENTRY - 1)

    new_bars = _bars([100.0] * (LOOKBACK_ENTRY + 2))
    assert signal(new_bars, 0) is False


def test_signal_does_not_use_future_bars():
    prefix = [100.0] * LOOKBACK_ENTRY + [101.0, 101.0]
    bars = _bars(prefix)
    full = _bars(prefix + [50.0, 50.0, 50.0])

    for index in range(len(prefix)):
        left = DonchianSignal()(bars, index)
        right = DonchianSignal()(full, index)
        assert left == right


def test_current_bar_high_does_not_set_entry_level():
    closes = [100.0] * LOOKBACK_ENTRY + [101.0]
    highs = [100.0] * LOOKBACK_ENTRY + [500.0]
    bars = _bars(closes, highs=highs)
    signal = DonchianSignal()

    assert signal(bars, LOOKBACK_ENTRY) is True
