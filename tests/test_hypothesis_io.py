import unittest

from trading_research.hypothesis_io import hypothesis_to_json, parse_hypothesis_json


class HypothesisIOTests(unittest.TestCase):
    def _payload(self):
        return '''{
          "name": "trend-following-test",
          "thesis": "A breakout after sustained directional movement has positive expectancy.",
          "symbol": "EURUSD",
          "timeframe": "M15",
          "rules": {
            "entry": "close above prior 20-bar high",
            "exit": "close below prior 10-bar low"
          },
          "expected_edge": "Positive expectancy after costs.",
          "falsifier": "Validation expectancy is not positive.",
          "rationale": "Explicit test hypothesis."
        }'''

    def test_parse_valid_hypothesis(self):
        hypothesis = parse_hypothesis_json(self._payload())
        self.assertEqual(hypothesis.symbol, "EURUSD")
        self.assertEqual(hypothesis.rules["entry"], "close above prior 20-bar high")

    def test_rejects_extra_fields(self):
        payload = self._payload()[:-1] + ', "execute_now": true}'
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            parse_hypothesis_json(payload)

    def test_rejects_missing_falsifier(self):
        payload = self._payload().replace('"falsifier": "Validation expectancy is not positive.",', '')
        with self.assertRaisesRegex(ValueError, "missing fields"):
            parse_hypothesis_json(payload)

    def test_round_trip_is_deterministic(self):
        hypothesis = parse_hypothesis_json(self._payload())
        serialized = hypothesis_to_json(hypothesis)
        restored = parse_hypothesis_json(serialized)
        self.assertEqual(restored, hypothesis)


if __name__ == "__main__":
    unittest.main()
