from trading_research.rebuild_recovery_manifest import rebuild_manifest


def test_recovery_manifest_builder_imports() -> None:
    assert callable(rebuild_manifest)
