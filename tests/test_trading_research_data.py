import tempfile
import unittest
from pathlib import Path

from trading_research.data import Bar, chronological_split, load_csv


class TradingResearchDataTests(unittest.TestCase):
    def _bars(self, count=10):
        from datetime import datetime, timedelta, timezone

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return tuple(
            Bar(
                timestamp=start + timedelta(hours=index),
                open=100 + index,
                high=101 + index,
                low=99 + index,
                close=100.5 + index,
                volume=1000,
            )
            for index in range(count)
        )

    def test_split_is_chronological_and_non_overlapping(self):
        bars = self._bars(10)
        split = chronological_split(bars, train_ratio=0.6, validation_ratio=0.2)
        self.assertEqual(len(split.train), 6)
        self.assertEqual(len(split.validation), 2)
        self.assertEqual(len(split.test), 2)
        self.assertLess(split.train[-1].timestamp, split.validation[0].timestamp)
        self.assertLess(split.validation[-1].timestamp, split.test[0].timestamp)

    def test_csv_loader_rejects_unordered_timestamps(self):
        content = "timestamp,open,high,low,close,volume\n"
        content += "2026-01-01T01:00:00Z,1,2,0.5,1.5,10\n"
        content += "2026-01-01T00:00:00Z,1,2,0.5,1.5,10\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bars.csv"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "chronological"):
                load_csv(path)

    def test_csv_loader_accepts_valid_ohlcv(self):
        content = "timestamp,open,high,low,close,volume\n"
        content += "2026-01-01T00:00:00Z,1,2,0.5,1.5,10\n"
        content += "2026-01-01T01:00:00Z,1.5,2.5,1,2,11\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bars.csv"
            path.write_text(content, encoding="utf-8")
            bars = load_csv(path)
            self.assertEqual(len(bars), 2)
            self.assertEqual(bars[0].close, 1.5)

    def test_bar_rejects_impossible_range(self):
        bar = Bar(
            timestamp=self._bars(1)[0].timestamp,
            open=2,
            high=1,
            low=0,
            close=1.5,
            volume=1,
        )
        with self.assertRaisesRegex(ValueError, "high"):
            bar.validate()


if __name__ == "__main__":
    unittest.main()
