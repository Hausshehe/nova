from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from trading_research.horizon_robustness_runner import _parser, run
from trading_research.data import Bar


def _write_csv(path) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lines = ["timestamp,open,high,low,close,volume"]
    for index in range(60):
        price = 100.0 + index
        timestamp = (start + timedelta(minutes=index)).isoformat()
        lines.append(f"{timestamp},{price},{price + 1},{price - 1},{price},1")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_runner_returns_json_serializable_audit(tmp_path) -> None:
    csv_path = tmp_path / "bars.csv"
    _write_csv(csv_path)
    result = run(str(csv_path), min_history=0, cost_grid_bps=(0.0, 4.0, 8.0))
    payload = json.dumps(result)
    assert result["runner"] == "horizon_robustness_runner"
    assert result["research_status"] == "diagnostic_only"
    assert result["total_bars"] == 60
    assert payload


def test_runner_parser_keeps_cost_grid_evaluation_only() -> None:
    args = _parser().parse_args(["bars.csv", "--cost-grid-bps", "0", "4", "8"])
    assert args.training_cost_bps == 4.0
    assert args.cost_grid_bps == [0.0, 4.0, 8.0]
