from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


RECOVERY_WORKFLOWS = {
    "recover-broader-campaign.yml",
    "recover-broader-campaign-safe.yml",
    "recover-broader-campaign-final.yml",
    "run-broader-replication.yml",
}


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_recovery_workflows_do_not_have_outer_attempt_retry_loops() -> None:
    forbidden_fragments = (
        "for attempt in range(1, 4)",
        "attempt={attempt}/3",
        "recovery_exhausted:",
    )
    for name in RECOVERY_WORKFLOWS:
        content = _read(name)
        for fragment in forbidden_fragments:
            assert fragment not in content, f"{name} reintroduced deterministic retry loop: {fragment}"


def test_development_benchmark_does_not_restore_stale_acquisition_commit() -> None:
    content = _read("experiment2-development-benchmark.yml")
    assert "git checkout 823545c49d560837bc53ade89213bdeed203b9bf -- trading_research/dukascopy_history.py" not in content
    assert "Restore verified historical acquisition module" not in content


def test_recovery_workflows_upload_partial_failure_evidence_without_secondary_failure() -> None:
    for name in RECOVERY_WORKFLOWS:
        content = _read(name)
        assert "if-no-files-found: warn" in content, f"{name} can hide the real failure behind artifact-upload failure"


def test_campaign_recovery_entrypoints_share_one_serialized_lock() -> None:
    expected = "group: nova-broader-campaign-recovery"
    for name in RECOVERY_WORKFLOWS:
        content = _read(name)
        assert "concurrency:" in content, f"{name} can race a sibling campaign workflow"
        assert expected in content, f"{name} is outside the shared campaign lock"
        assert "cancel-in-progress: false" in content, f"{name} can cancel a valid campaign run"


def test_independent_replication_never_uses_stale_hardcoded_sources() -> None:
    content = _read("run-broader-replication.yml")
    assert "ref: 25dff152e4f65d64c7b999fefda8384970c5657c" not in content
    assert "run-id: 32293018258" not in content
    assert "source_run_id:" in content
    assert "research_commit:" in content


def test_research_ci_does_not_stack_obsolete_runs() -> None:
    content = _read("trading-research-tests.yml")
    assert "concurrency:" in content
    assert "trading-research-tests-${{ github.workflow }}-${{ github.ref }}" in content
    assert "cancel-in-progress: true" in content


def test_final_recovery_workflow_serializes_campaign_runs() -> None:
    content = _read("recover-broader-campaign-final.yml")
    assert "concurrency:" in content
    assert "group: nova-broader-campaign-recovery" in content
    assert "cancel-in-progress: false" in content


def test_recovery_universe_compatibility_exports_match_canonical_constants() -> None:
    from trading_research.data import INSTRUMENTS as exported_instruments, TIMEFRAMES as exported_timeframes
    from trading_research.dukascopy_history import INSTRUMENTS, TIMEFRAMES

    assert exported_instruments == INSTRUMENTS
    assert exported_timeframes == TIMEFRAMES
