from __future__ import annotations

import pytest

from trading_research.memory import ExperienceStore


BASE = {
    "hypothesis": {
        "name": "sample",
        "symbol": "EURUSD",
        "timeframe": "1H",
        "rules": {"entry": "close_above_ma"},
    },
    "dataset": "EURUSD_1H.csv",
    "final_decision": "REJECT",
}


def _record(**overrides: object) -> dict:
    payload = dict(BASE)
    payload.update(overrides)
    return payload


def _write(store: ExperienceStore, record: dict, *, experiment_id: str = "exp-fixed") -> None:
    store.record_experiment(
        experiment_id=experiment_id,
        created_at_utc="2026-08-20T00:00:00+00:00",
        hypothesis_name="sample",
        symbol="EURUSD",
        timeframe="1H",
        final_decision="REJECT",
        record=record,
    )


def test_identical_experiment_record_is_idempotent(tmp_path) -> None:
    store = ExperienceStore(tmp_path / "memory.sqlite")
    record = _record()

    _write(store, record)
    _write(store, record)

    assert store.list_experiment_hypotheses() == [record["hypothesis"]]


def test_conflicting_experiment_id_fails_closed(tmp_path) -> None:
    store = ExperienceStore(tmp_path / "memory.sqlite")
    _write(store, _record())

    conflicting = _record(dataset="OTHER.csv")
    with pytest.raises(ValueError, match="experiment_id_conflict:exp-fixed"):
        _write(store, conflicting)

    assert store.list_experiment_hypotheses() == [BASE["hypothesis"]]
