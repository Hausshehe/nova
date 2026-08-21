from datetime import datetime, timedelta, timezone

from trading_research.context_selector_development import (
    DEVELOPMENT_FRACTION,
    evaluate_context,
)
from trading_research.data import Bar


def _bars(n=520):
    bars = []
    price = 100.0
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        # Deterministic alternating drift plus changing range creates enough
        # structure for both global and contextual selectors to execute.
        drift = 0.001 if (i // 40) % 2 == 0 else -0.0007
        price *= 1.0 + drift
        bars.append(
            Bar(
                timestamp=(start + timedelta(hours=i)).isoformat(),
                open=price * 0.999,
                high=price * (1.0 + 0.002 + (i % 3) * 0.0002),
                low=price * (0.998 - (i % 2) * 0.0002),
                close=price,
                volume=1.0,
            )
        )
    return bars


def _write_csv(path, bars):
    import csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for bar in bars:
            writer.writerow([
                bar.timestamp,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
            ])


def test_context_selector_reserves_final_fraction():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "demo.csv"
        _write_csv(path, _bars())
        result = evaluate_context("DEMO", "1D", path)

    assert result.total_bars == 520
    assert result.development_bars == int(520 * DEVELOPMENT_FRACTION)
    assert result.final_reserved_bars == 520 - result.development_bars
    assert result.final_reserved_bars > 0


def test_context_selector_outputs_paired_comparison():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "demo.csv"
        _write_csv(path, _bars())
        result = evaluate_context("DEMO", "1D", path)

    assert result.global_decisions >= 0
    assert result.contextual_decisions >= 0
    assert result.contextual_minus_global_bps == (
        result.contextual_mean_net_bps - result.global_mean_net_bps
    )
