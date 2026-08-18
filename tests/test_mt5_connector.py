import unittest
from datetime import datetime, timezone

from trading_research.mt5_connector import MT5Config, MT5ConnectionError, MT5MarketData


class FakeMT5:
    def __init__(self):
        self.initialized = False
        self.shutdown_called = False
        self.last_error_value = (0, "")

    def initialize(self, *args, **kwargs):
        self.initialized = True
        self.initialize_args = args
        self.initialize_kwargs = kwargs
        return True

    def shutdown(self):
        self.shutdown_called = True

    def last_error(self):
        return self.last_error_value

    def copy_rates_range(self, symbol, timeframe, date_from, date_to):
        self.bars_args = (symbol, timeframe, date_from, date_to)
        return [{"time": 1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}]

    def copy_ticks_range(self, symbol, date_from, date_to, flags):
        self.ticks_args = (symbol, date_from, date_to, flags)
        return [{"time": 1, "bid": 1.0, "ask": 1.1}]


class MT5ConnectorTests(unittest.TestCase):
    def test_connect_and_close_are_read_only_lifecycle(self):
        fake = FakeMT5()
        connector = MT5MarketData(MT5Config(), module=fake)
        connector.connect()
        self.assertTrue(fake.initialized)
        self.assertTrue(connector._connected)
        connector.close()
        self.assertTrue(fake.shutdown_called)
        self.assertFalse(connector._connected)

    def test_bars_forces_utc_and_returns_provider_data(self):
        fake = FakeMT5()
        connector = MT5MarketData(module=fake)
        connector.connect()
        data = connector.bars(
            " EURUSD ",
            5,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(data[0]["close"], 1.5)
        self.assertEqual(fake.bars_args[0], "EURUSD")
        self.assertEqual(fake.bars_args[2].tzinfo, timezone.utc)

    def test_ticks_requires_aware_ascending_interval(self):
        connector = MT5MarketData(module=FakeMT5())
        connector.connect()
        with self.assertRaises(ValueError):
            connector.ticks(
                "EURUSD",
                datetime(2026, 1, 2),
                datetime(2026, 1, 3, tzinfo=timezone.utc),
                3,
            )
        with self.assertRaises(ValueError):
            connector.ticks(
                "EURUSD",
                datetime(2026, 1, 3, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
                3,
            )

    def test_bars_requires_connection(self):
        connector = MT5MarketData(module=FakeMT5())
        with self.assertRaises(MT5ConnectionError):
            connector.bars(
                "EURUSD",
                5,
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
