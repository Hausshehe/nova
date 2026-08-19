from trading_research.evidence_identity import recorded_dataset_sha256, same_evidence, sha256_file


def test_sha256_file_is_deterministic(tmp_path) -> None:
    path = tmp_path / "data.csv"
    path.write_bytes(b"EURUSD,1.0\n")
    digest = sha256_file(path)
    assert digest is not None
    assert digest == sha256_file(path)


def test_recorded_dataset_identity_survives_missing_old_file() -> None:
    record = {"dataset_sha256": "a" * 64, "dataset": "/gone/old.csv"}
    assert recorded_dataset_sha256(record) == "a" * 64
    assert same_evidence(record, "a" * 64)


def test_missing_recorded_identity_is_not_treated_as_matching() -> None:
    record = {"dataset": "/gone/old.csv"}
    assert recorded_dataset_sha256(record) is None
    assert not same_evidence(record, "a" * 64)
