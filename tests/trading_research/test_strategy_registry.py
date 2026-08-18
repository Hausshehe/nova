from trading_research.memory import ExperienceStore
from trading_research.strategy_registry import Strategy, StrategyRegistry


def test_registry_keeps_research_state_separate_from_lifecycle(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    registry = StrategyRegistry(store)

    registry.register(
        Strategy(
            name="eurusd_breakout",
            version="1.0",
            status="CANDIDATE",
            research_state="OOS_VALIDATED",
            hypothesis={"entry": "breakout", "symbol": "EURUSD"},
        )
    )

    saved = store.get_strategy("eurusd_breakout", "1.0")
    assert saved is not None
    assert saved["status"] == "CANDIDATE"
    assert saved["hypothesis"]["research_state"] == "OOS_VALIDATED"
    assert saved["approved_at_utc"] is None


def test_registry_blocks_approval_before_oos_validation(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    registry = StrategyRegistry(store)
    registry.register(
        Strategy(
            name="eurusd_breakout",
            version="1.0",
            status="CANDIDATE",
            research_state="PROMISING",
            hypothesis={"entry": "breakout"},
        )
    )

    try:
        registry.approve("eurusd_breakout", "1.0")
    except ValueError as exc:
        assert "OOS_VALIDATED" in str(exc)
    else:
        raise AssertionError("approval must require OOS_VALIDATED")


def test_registry_approval_is_explicit_and_timestamped(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    registry = StrategyRegistry(store)
    registry.register(
        Strategy(
            name="eurusd_breakout",
            version="1.0",
            status="CANDIDATE",
            research_state="OOS_VALIDATED",
            hypothesis={"entry": "breakout"},
        )
    )

    registry.approve("eurusd_breakout", "1.0", reason="external approval gate passed")
    saved = store.get_strategy("eurusd_breakout", "1.0")
    assert saved is not None
    assert saved["status"] == "APPROVED"
    assert saved["approved_at_utc"]
