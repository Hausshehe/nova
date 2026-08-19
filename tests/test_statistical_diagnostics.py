import pytest

from trading_research.statistical_diagnostics import (
    DEFAULT_BLOCK_LENGTHS,
    bootstrap_block_sensitivity,
    compare_frozen_streams,
    moving_block_bootstrap_mean_ci,
)


def test_bootstrap_is_reproducible_and_contains_sample_mean_for_constant_data():
    result = moving_block_bootstrap_mean_ci([2.0] * 20, block_length=5, samples=100, seed=7)
    assert result["sample_mean"] == 2.0
    assert result["ci_lower"] == 2.0
    assert result["ci_upper"] == 2.0


def test_bootstrap_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        moving_block_bootstrap_mean_ci([], block_length=1)
    with pytest.raises(ValueError):
        moving_block_bootstrap_mean_ci([1.0, 2.0], block_length=3)
    with pytest.raises(ValueError):
        moving_block_bootstrap_mean_ci([1.0, 2.0], samples=0)


def test_compare_streams_reports_difference_without_selection():
    result = compare_frozen_streams([1.0, 2.0, 3.0], [0.0, 1.0, 2.0], block_length=2, samples=50)
    assert result["difference_of_means"] == 1.0
    assert result["left"]["sample_mean"] == 2.0
    assert result["right"]["sample_mean"] == 1.0


def test_block_sensitivity_reports_every_predeclared_length_without_selection():
    result = bootstrap_block_sensitivity([1.0, 2.0, 3.0, 4.0] * 5, samples=50, seed=3)
    assert tuple(int(key) for key in result) == DEFAULT_BLOCK_LENGTHS
    assert all(entry["sample_mean"] == 2.5 for entry in result.values())


def test_block_sensitivity_rejects_invalid_grid():
    with pytest.raises(ValueError):
        bootstrap_block_sensitivity([1.0, 2.0], block_lengths=[])
    with pytest.raises(ValueError):
        bootstrap_block_sensitivity([1.0, 2.0], block_lengths=[1, 1])
