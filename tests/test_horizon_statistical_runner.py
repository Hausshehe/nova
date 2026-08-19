import pytest

from trading_research.horizon_statistical_runner import run


def test_statistical_runner_rejects_invalid_cost(tmp_path):
    with pytest.raises(ValueError):
        run(str(tmp_path / "missing.csv"), cost_bps=-1.0)


def test_statistical_runner_rejects_invalid_bootstrap_settings(tmp_path):
    with pytest.raises(ValueError):
        run(str(tmp_path / "missing.csv"), block_length=0)
    with pytest.raises(ValueError):
        run(str(tmp_path / "missing.csv"), samples=0)
