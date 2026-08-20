import importlib
import traceback

MODULES = (
    "trading_research.migrate_legacy_broader_artifacts",
    "trading_research.rebuild_recovery_manifest",
)


def test_recovery_workflow_import_contract() -> None:
    for module_name in MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            traceback.print_exc()
            raise
        assert module is not None
