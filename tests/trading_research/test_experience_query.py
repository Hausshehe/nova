from trading_research.contracts import Hypothesis
from trading_research.experience_query import ExperienceQuery
from trading_research.memory import ExperienceStore


def hypothesis() -> Hypothesis:
    return Hypothesis(
        name="query_test_hypothesis",
        thesis="read prior research history",
        symbol="EURUSD",
        timeframe="1D",
        rules={"signal": "fixed"},
        expected_edge="test only",
        falsifier="reject on negative evidence",
        rationale="query facade test",
    )


def record(store: ExperienceStore, experiment_id: str, observed_at: str, decision: str) -> None:
    h = hypothesis()
    store.record_experiment(
        experiment_id=experiment_id,
        created_at_utc=observed_at,
        hypothesis_name=h.name,
        symbol=h.symbol,
        timeframe=h.timeframe,
        final_decision=decision,
        record={
            "schema_version": 1,
            "created_at_utc": observed_at,
            "hypothesis": {
                "name": h.name,
                "thesis": h.thesis,
                "symbol": h.symbol,
                "timeframe": h.timeframe,
                "rules": dict(h.rules),
                "expected_edge": h.expected_edge,
                "falsifier": h.falsifier,
                "rationale": h.rationale,
            },
            "dataset": "",
            "dataset_sha256": "a" * 64,
            "final_decision": decision,
            "segments": [],
            "costs": {"fee_bps_per_side": 1.0, "slippage_bps_per_side": 1.0},
        },
    )


def test_history_and_dispositions_are_read_only() -> None:
    store = ExperienceStore(":memory:")
    record(store, "old", "2026-01-01T00:00:00+00:00", "REJECT")
    record(store, "new", "2026-02-01T00:00:00+00:00", "INCONCLUSIVE")

    query = ExperienceQuery(store)
    history = query.history_for_hypothesis(hypothesis())

    assert [item.experiment_id for item in history] == ["old", "new"]
    assert query.prior_dispositions(hypothesis()) == ("REJECT", "INCONCLUSIVE")


def test_available_history_excludes_future_evidence() -> None:
    store = ExperienceStore(":memory:")
    record(store, "old", "2026-01-01T00:00:00+00:00", "REJECT")
    record(store, "new", "2026-02-01T00:00:00+00:00", "INCONCLUSIVE")

    available = ExperienceQuery(store).available_history(
        hypothesis(),
        "2026-01-15T00:00:00+00:00",
    )

    assert [item.experiment_id for item in available] == ["old"]


def test_explain_experiment_returns_evidence_without_mutating_memory() -> None:
    store = ExperienceStore(":memory:")
    record(store, "old", "2026-01-01T00:00:00+00:00", "REJECT")

    explained = ExperienceQuery(store).explain_experiment("old")

    assert explained is not None
    assert explained["experiment_id"] == "old"
    assert explained["final_decision"] == "REJECT"
    assert explained["knowledge_class"] == "REJECTED"
    assert ExperienceQuery(store).history_for_hypothesis(hypothesis())[0].experiment_id == "old"
