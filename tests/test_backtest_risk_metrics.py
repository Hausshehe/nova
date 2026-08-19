from datetime import datetime, timedelta, timezone

from trading_research.backtest import run_long_flat
from trading_research.data import Bar


def _bars() -> list[Bar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = [100.0, 100.0, 90.0, 95.0]
    bars: list[Bar] = []
    for index, close in enumerate(closes):
        bars.append(
            Bar(
                timestamp=start + timedelta(days=index),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1.0,
            )
        )
    return bars


def test_max_drawdown_includes_intra_trade_loss():
    result = run_long_flat(_bars(), lambda _bars, index: index < 2)
    assert result.trades
    assert min(result.equity_curve) < 0.95
    assert result.max_drawdown > 0.09


def test_final_return_remains_realized_trade_return():
    result = run_long_flat(_bars(), lambda _bars, index: index < 2)
    assert result.final_return == result.trades[0].return_fraction
