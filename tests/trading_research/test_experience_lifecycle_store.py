from trading_research.experience_lifecycle import ExperienceMetadata
from trading_research.experience_lifecycle_store import ExperienceLifecycleStore


def _metadata(experiment_id: str, knowledge_class: str, parent: str | None = None) -> ExperienceMetadata:
    return ExperienceMetadata(
        experiment_id=experiment_id,
        observed_at_utc="2026-01-01T00:00:00+00:00",
        hypothesis_fingerprint="a" * 64,
        dataset_sha256="b" * 64,
        final_decision="REJECT",
        knowledge_class=knowledge_class,
        parent_experiment_id=parent,
    )


def test_lifecycle_metadata_is_durable_and_idempotent() -> None:
    store = ExperienceLifecycleStore(":memory:")
    item = _metadata("exp-1", "HISTORICAL_RESEARCH")
    store.record(item)
    store.record(item)
    assert store.get("exp-1") == item


def test_lifecycle_store_rejects_conflicting_metadata() -> None:
    store = ExperienceLifecycleStore(":memory:")
    store.record(_metadata("exp-1", "HISTORICAL_RESEARCH"))
    try:
        store.record(_metadata("exp-1", "INDEPENDENT_VALIDATION"))
    except ValueError as exc:
        assert str(exc) == "experience lifecycle already exists with different metadata: exp-1"
    else:
        raise AssertionError("expected conflicting lifecycle metadata to fail")
