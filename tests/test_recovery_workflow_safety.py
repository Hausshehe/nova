from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


RECOVERY_WORKFLOWS = {
    "recover-broader-campaign.yml",
    "recover-broader-campaign-safe.yml",
    "recover-broader-campaign-final.yml",
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


def test_final_recovery_workflow_serializes_campaign_runs() -> None:
    content = _read("recover-broader-campaign-final.yml")
    assert "concurrency:" in content
    assert "group: nova-broader-campaign-recovery" in content
    assert "cancel-in-progress: false" in content
