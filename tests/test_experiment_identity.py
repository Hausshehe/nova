from __future__ import annotations

from trading_research.autonomous_research import _experiment_id


class _Record:
    def __init__(self, created_at_utc: str) -> None:
        self._created_at_utc = created_at_utc

    def to_dict(self) -> dict:
        return {
            "created_at_utc": self._created_at_utc,
            "hypothesis": {
                "name": "test-hypothesis",
                "thesis": "same thesis",
                "symbol": "EURUSD",
                "timeframe": "1D",
                "rules": {"signal": "close_above_open"},
                "expected_edge": "positive drift",
                "falsifier": "negative expectancy",
                "rationale": "identity regression test",
            },
            "dataset": "data/research/EURUSD_1D.csv",
            "total_bars": 1000,
            "split_sizes": {"train": 600, "validation": 200, "test": 200},
            "costs": {"fee_bps_per_side": 1.0, "slippage_bps_per_side": 1.0},
            "segments": [],
            "final_decision": "REJECT",
        }


def test_experiment_id_is_independent_of_execution_timestamp() -> None:
    first = _experiment_id(_Record("2026-08-20T18:00:00+00:00"))
    second = _experiment_id(_Record("2026-08-20T19:00:00+00:00"))
    assert first == second
    assert first.startswith("exp-")
