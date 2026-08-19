from pathlib import Path


def test_runner_module_imports() -> None:
    from trading_research import gap_continuation_runner

    assert callable(gap_continuation_runner.main)


def test_fixture_path_can_be_constructed(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-02T00:00:00+00:00,1.10,1.11,1.09,1.10,100\n",
        encoding="utf-8",
    )
    assert path.exists()
