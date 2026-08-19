from datetime import time

from trading_research.constitution_runtime import validate_demo_runtime
from trading_research.trading_constitution import TradingConstitution


def test_runtime_allows_valid_demo_state():
    result = validate_demo_runtime(
        TradingConstitution(),
        demo_mode=True,
        daily_loss_fraction=0.0,
        open_positions=0,
        spread_bps=2.0,
        session_time=time(10, 0),
    )
    assert result.allowed is True
    assert result.reason == "trading_constitution_passed"


def test_runtime_blocks_non_demo_mode():
    result = validate_demo_runtime(TradingConstitution(), demo_mode=False)
    assert result.allowed is False
    assert result.reason == "trading_constitution_requires_demo_mode"


def test_runtime_blocks_risk_and_session_boundaries():
    constitution = TradingConstitution()
    assert not validate_demo_runtime(
        constitution,
        demo_mode=True,
        daily_loss_fraction=0.02,
        session_time=time(10, 0),
    ).allowed
    assert not validate_demo_runtime(
        constitution,
        demo_mode=True,
        session_time=time(16, 0),
    ).allowed
