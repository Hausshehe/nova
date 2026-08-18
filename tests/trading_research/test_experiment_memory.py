from types import SimpleNamespace

from trading_research.memory import ExperienceStore
from tools.run_first_research_experiment import persist_experiment


def test_persist_experiment_records_result(tmp_path):
    record = SimpleNamespace(
        created_at_utc="2026-08-19T00:00:00+00:00",
        hypothesis=SimpleNamespace(
            name="test_strategy",
            symbol="EURUSD",
            timeframe="1D",
        ),
        final_decision=SimpleNamespace(value="REJECT"),
    )
    payload = {
        "schema_version": 1,
        "hypothesis": {"name": "test_strategy"},
        "final_decision": "REJECT",
    }

    memory = tmp_path / "experience.sqlite3"
    experiment_id = persist_experiment(record, payload, memory, None)

    assert experiment_id.startswith("exp-")
    store = ExperienceStore(memory)
    with store._connect() as db:
        row = db.execute(
            "SELECT experiment_id, hypothesis_name, final_decision FROM experiments"
        ).fetchone()

    assert row["experiment_id"] == experiment_id
    assert row["hypothesis_name"] == "test_strategy"
    assert row["final_decision"] == "REJECT"
