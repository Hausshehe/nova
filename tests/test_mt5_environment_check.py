import unittest

from tools.check_mt5_environment import _normalize_rows, _timeframe_value


class MT5EnvironmentCheckTests(unittest.TestCase):
    def test_timeframe_name_resolves_from_fake_module(self):
        class FakeMT5:
            TIMEFRAME_M15 = 15

        self.assertEqual(_timeframe_value(FakeMT5, "m15"), 15)

    def test_normalize_rows_uses_utc_and_research_schema(self):
        rows = [
            {
                "time": 1700000000,
                "open": 1.1,
                "high": 1.2,
                "low": 1.0,
                "close": 1.15,
                "tick_volume": 42,
            }
        ]
        result = _normalize_rows([rows[0]])
        self.assertEqual(result[0]["timestamp"], "2023-11-14T22:13:20+00:00")
        self.assertEqual(result[0]["volume"], 42.0)
        self.assertEqual(set(result[0]), {"timestamp", "open", "high", "low", "close", "volume"})


if __name__ == "__main__":
    unittest.main()
