import json

from trading_research.memory import ExperienceStore, TradeRecord


def _trade(*, trade_id="T1", pnl=12.5, outcome="WIN"):
    return TradeRecord(
        trade_id=trade_id,
        strategy_name="eurusd_breakout",
        strategy_version="v1",
        symbol="EURUSD",
        timeframe="15M",
        direction="LONG",
        entry_price=1.1000,
        exit_price=1.1020,
        quantity=0.1,
        pnl=pnl,
        outcome=outcome,
        opened_at="2026-01-01T09:00:00+00:00",
        closed_at="2026-01-01T10:00:00+00:00",
        market_state={"trend": "bullish", "spread": 0.8},
    )


def test_memory_store_persists_experiment_and_strategy(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    record = {"schema_version": 1, "final_decision": "REJECT"}
    store.record_experiment(
        experiment_id="001",
        created_at_utc="2026-01-01T00:00:00+00:00",
        hypothesis_name="baseline",
        symbol="EURUSD",
        timeframe="1D",
        final_decision="REJECT",
        record=record,
    )
    store.register_strategy(
        strategy_name="baseline",
        strategy_version="v1",
        status="CANDIDATE",
        hypothesis={"name": "baseline"},
    )

    with __import__("sqlite3").connect(tmp_path / "experience.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM strategies").fetchone()[0] == 1
        assert json.loads(db.execute("SELECT record_json FROM experiments").fetchone()[0]) == record


def test_trade_journal_and_summary(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    store.record_trade(_trade(pnl=10.0, outcome="WIN"))
    store.record_trade(_trade(trade_id="T2", pnl=-4.0, outcome="LOSS"))

    trades = store.list_strategy_trades("eurusd_breakout", "v1")
    assert [trade.trade_id for trade in trades] == ["T1", "T2"]
    assert trades[0].market_state["trend"] == "bullish"

    summary = store.strategy_performance_summary("eurusd_breakout", "v1")
    assert summary["closed_trades"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["net_pnl"] == 6.0
    assert summary["profit_factor"] == 2.5


def test_trade_validation_rejects_unsafe_shape(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    bad = _trade()
    bad = TradeRecord(**{**bad.__dict__, "direction": "BUY"})
    try:
        store.record_trade(bad)
    except ValueError as exc:
        assert "LONG or SHORT" in str(exc)
    else:
        raise AssertionError("invalid direction should be rejected")
