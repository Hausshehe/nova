import pytest

from trading_research.research_universe import (
    ASSET_FAMILIES,
    HYPOTHESIS_FAMILIES,
    MAX_CONTEXTS,
    TIMEFRAMES,
    ResearchContext,
    all_instruments,
    build_research_universe,
    validate_context,
)


def test_universe_size_and_expected_dimensions():
    universe = build_research_universe()
    assert len(universe) == MAX_CONTEXTS == 104
    assert len(all_instruments()) == 13
    assert len(TIMEFRAMES) == 2
    assert len(HYPOTHESIS_FAMILIES) == 4
    assert {item.timeframe for item in universe} == set(TIMEFRAMES)
    assert {item.hypothesis_family for item in universe} == set(HYPOTHESIS_FAMILIES)


def test_universe_contains_no_duplicate_contexts():
    universe = build_research_universe()
    assert len(set(universe)) == len(universe)


@pytest.mark.parametrize(
    "context",
    [
        ResearchContext("FX_MAJOR", "EURUSD", "1D", "momentum_continuation"),
        ResearchContext("INDEX", "US500", "4H", "breakout_volatility_expansion"),
        ResearchContext("COMMODITY", "XAUUSD", "1D", "mean_reversion"),
    ],
)
def test_valid_contexts_are_accepted(context):
    validate_context(context)


def test_invalid_context_is_rejected():
    with pytest.raises(ValueError, match="instrument is not valid"):
        validate_context(ResearchContext("FX_MAJOR", "US500", "1D", "mean_reversion"))
