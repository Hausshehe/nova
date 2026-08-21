from datetime import datetime, timedelta, timezone

from trading_research.context_selector_final import evaluate_context
from trading_research.contextual_online_expert_ensemble import evaluate_contextual_online_expert_ensemble
from trading_research.data import Bar
from trading_research.online_expert_ensemble import evaluate_online_expert_ensemble


def _bars(n=320):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    bars = []
    for i in range(n):
        drift = 0.001 if (i // 32) % 2 == 0 else -0.0008
        price *= 1.0 + drift
        bars.append(
            Bar(
                timestamp=start + timedelta(hours=i),
                open=price * 0.999,
                high=price * 1.002,
                low=price * 0.998,
                close=price,
                volume=1.0,
            )
        )
    return bars


def test_online_selectors_report_only_final_window():
    bars = _bars()
    start = int(len(bars) * 0.8)
    global_result = evaluate_online_expert_ensemble(
        bars, min_history=0, evaluation_start_index=start
    )
    contextual_result = evaluate_contextual_online_expert_ensemble(
        bars,
        min_global_history=0,
        min_context_history=0,
        evaluation_start_index=start,
    )
    assert global_result["parameters"]["evaluation_start_index"] == start
    assert contextual_result["parameters"]["evaluation_start_index"] == start
    assert global_result["candidate_bars"] <= len(bars) - start
    assert contextual_result["candidate_bars"] <= len(bars) - start


def test_final_context_result_reserves_development_boundary():
    import tempfile
    from pathlib import Path
    import csv

    bars = _bars()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "demo.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for bar in bars:
                writer.writerow([
                    bar.timestamp.isoformat(),
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                ])
        result = evaluate_context("DEMO", "1D", path)

    assert result.development_bars == int(len(bars) * 0.8)
    assert result.final_test_bars == len(bars) - result.development_bars
