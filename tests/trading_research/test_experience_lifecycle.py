from trading_research.experience_lifecycle import (
    ExperienceMetadata,
    available_at_or_before,
    classify_research_result,
    validate_lineage,
)


def experience(experiment_id: str, observed_at: str, parent: str | None = None) -> ExperienceMetadata:
    return ExperienceMetadata(
        experiment_id=experiment_id,
        observed_at_utc=observed_at,
        hypothesis_fingerprint="a" * 64,
        dataset_sha256="b" * 64,
        final_decision="REJECT",
        knowledge_class="REJECTED",
        parent_experiment_id=parent,
    )


def test_future_evidence_is_not_available_to_an_earlier_decision() -> None:
    items = [
        experience("old", "2026-01-01T00:00:00+00:00"),
        experience("new", "2026-02-01T00:00:00+00:00"),
    ]
    available = available_at_or_before(items, "2026-01-15T00:00:00+00:00")
    assert [item.experiment_id for item in available] == ["old"]


def test_lineage_requires_existing_parent() -> None:
    child = experience("child", "2026-02-01T00:00:00+00:00", parent="parent")
    validate_lineage(child, {"parent"})


def test_lineage_fails_closed_for_missing_parent() -> None:
    child = experience("child", "2026-02-01T00:00:00+00:00", parent="missing")
    try:
        validate_lineage(child, set())
    except ValueError as exc:
        assert str(exc) == "parent_experiment_not_found"
    else:
        raise AssertionError("expected missing parent to fail closed")


def test_research_dispositions_map_to_explicit_classes() -> None:
    assert classify_research_result("REJECT") == "REJECTED"
    assert classify_research_result("INCONCLUSIVE") == "INCONCLUSIVE"
    assert classify_research_result("PROMISING") == "HISTORICAL_RESEARCH"
