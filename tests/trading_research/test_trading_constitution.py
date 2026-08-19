from datetime import time

import pytest

from trading_research.trading_constitution import TradingConstitution


def test_constitution_defaults_validate():
    constitution = TradingConstitution()
    constitution.validate()
    assert constitution.version == "1.0"
    assert constitution.demo_only is True
    assert constitution.normal_review_seconds == 15


def test_review_interval_is_clamped():
    constitution = TradingConstitution(minimum_review_seconds=2, maximum_review_seconds=30)
    assert constitution.review_interval_for(None) == 15
    assert constitution.review_interval_for(1) == 2
    assert constitution.review_interval_for(100) == 30


def test_invalid_session_window_rejected():
    constitution = TradingConstitution(session_start=time(16, 0), session_end=time(8, 0))
    with pytest.raises(ValueError):
        constitution.validate()


def test_constitution_serialization_is_explicit():
    payload = TradingConstitution().as_dict()
    assert payload["version"] == "1.0"
    assert payload["demo_only"] is True
    assert payload["require_deterministic_policy"] is True
