from datetime import datetime, timedelta, timezone

from trading_research.backtest import run_long_flat
from trading_research.data import Bar
from tools.run_first_research_experiment import signal


def _bars(count: int = 80) -> list[Bar]:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(count):
        # Deterministic up/down sequence; this test only checks execution,
        # not whether the hypothesis has an edge.
        close = 100.0 + i * 0.1
        rows.append(
            Bar(
                timestamp=start + timedelta(days=i),
                open=close,
                high=close + 0.2,
                low=close - 0.2,
                close=close,
                volume=1.0,
            )
        )
    return rows


def test_first_experiment_signal_is_deterministic_and_next_bar_safe():
    bars = _bars()
    result = run_long_flat(bars, signal, fee_bps=1.0, slippage_bps=1.0)
    assert result.trades
    assert result.trades[0].entry_timestamp == bars[50].timestamp
    assert result.trades[0].entry_price > bars[50].open
