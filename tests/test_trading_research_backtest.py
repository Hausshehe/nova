import unittest
from datetime import datetime, timedelta, timezone

from trading_research.backtest import run_long_flat
from trading_research.data import Bar


class TradingResearchBacktestTests(unittest.TestCase):
    def _bars(self, opens, closes=None):
        closes = closes or opens
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return tuple(
            Bar(
                timestamp=start + timedelta(hours=i),
                open=float(opens[i]),
                high=max(float(opens[i]), float(closes[i])) + 1,
                low=min(float(opens[i]), float(closes[i])) - 1,
                close=float(closes[i]),
                volume=1000,
            )
            for i in range(len(opens))
        )

    def test_entry_uses_next_bar_open_not_signal_bar_close(self):
        bars = self._bars([100, 110, 120], [100, 200, 120])
        result = run_long_flat(bars, lambda _bars, i: i == 0)
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].entry_price, 110.0)
        self.assertEqual(result.trades[0].exit_price, 120.0)

    def test_costs_reduce_return(self):
        bars = self._bars([100, 100, 110], [100, 100, 110])
        free = run_long_flat(bars, lambda _bars, i: i == 0)
        costly = run_long_flat(bars, lambda _bars, i: i == 0, fee_bps=10, slippage_bps=10)
        self.assertGreater(free.final_return, costly.final_return)

    def test_invalid_costs_rejected(self):
        bars = self._bars([100, 101])
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            run_long_flat(bars, lambda _bars, i: False, fee_bps=-1)

    def test_too_short_dataset_rejected(self):
        bars = self._bars([100])
        with self.assertRaisesRegex(ValueError, "at least two bars"):
            run_long_flat(bars, lambda _bars, i: True)


if __name__ == "__main__":
    unittest.main()
