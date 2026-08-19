import json

import pytest

from trading_research.experience_memory import ExperienceMemory, ExperienceRecord, experience_id


def _record(memory: ExperienceMemory, experiment: str = "exp-1") -> ExperienceRecord:
    return memory.record(
        experiment_id=experiment,
        hypothesis_id="h-8bar",
        domain="trading_research",
        event="experiment_completed",
        status="rejected",
        lesson="Fixed 8-bar did not survive non-overlapping validation.",
        strategy_version="v1",
        dataset_sha256="abc123",
        dataset_start="2012-12-04T00:00:00+00:00",
        dataset_end="2022-03-04T00:00:00+00:00",
        metrics={"mean_net_bps": -10.12},
        tags=("horizon", "rejected"),
        constraints=("causal", "no_live_trading"),
    )


def test_append_and_query_preserve_hash_chain(tmp_path):
    memory = ExperienceMemory(tmp_path / "experience.jsonl")
    first = _record(memory)
    second = _record(memory, "exp-2")

    assert first.previous_hash == "GENESIS"
    assert second.previous_hash == first.record_hash
    memory.validate_chain()
    assert memory.query(status="rejected") == (first, second)
    assert memory.query(tag="horizon") == (first, second)


def test_duplicate_experiment_is_rejected(tmp_path):
    memory = ExperienceMemory(tmp_path / "experience.jsonl")
    _record(memory)
    with pytest.raises(ValueError, match="already exists"):
        _record(memory)


def test_tampering_is_detected(tmp_path):
    path = tmp_path / "experience.jsonl"
    memory = ExperienceMemory(path)
    _record(memory)
    lines = path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload["lesson"] = "tampered"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        memory.all()


def test_record_hash_is_deterministic_for_same_payload():
    a = ExperienceRecord.create(
        experiment_id="exp-1",
        hypothesis_id="h",
        domain="research",
        event="completed",
        status="rejected",
        lesson="lesson",
        timestamp="2026-01-01T00:00:00+00:00",
        previous_hash="GENESIS",
    )
    b = ExperienceRecord.create(
        experiment_id="exp-1",
        hypothesis_id="h",
        domain="research",
        event="completed",
        status="rejected",
        lesson="lesson",
        timestamp="2026-01-01T00:00:00+00:00",
        previous_hash="GENESIS",
    )
    assert a.record_hash == b.record_hash


def test_experience_id_is_stable_and_dataset_sensitive():
    first = experience_id(hypothesis_id="h", dataset_sha256="a", experiment_name="exp")
    second = experience_id(hypothesis_id="h", dataset_sha256="a", experiment_name="exp")
    different = experience_id(hypothesis_id="h", dataset_sha256="b", experiment_name="exp")
    assert first == second
    assert first != different
