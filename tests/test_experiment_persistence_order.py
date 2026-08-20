from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_experiment_persists_evidence_before_strategy_sync() -> None:
    content = (ROOT / "trading_research" / "experiment.py").read_text(encoding="utf-8")
    evidence_marker = "        _record_experience(memory_store, record)"
    registry_marker = "        _sync_strategy_registry("
    evidence_index = content.index(evidence_marker)
    registry_index = content.index(registry_marker)
    assert evidence_index < registry_index


def test_autonomous_session_does_not_duplicate_experiment_persistence() -> None:
    content = (ROOT / "trading_research" / "autonomous_research.py").read_text(encoding="utf-8")
    assert "_record_experience(" not in content
