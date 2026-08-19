from trading_research.consensus_level_evaluation import LEVELS


def test_levels_are_predefined() -> None:
    assert LEVELS == (4, 5)
