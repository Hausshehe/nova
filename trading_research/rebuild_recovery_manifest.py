"""Rebuild the deterministic frozen-universe manifest after recovery."""

from __future__ import annotations

from pathlib import Path

from .verify_broader_universe import DEFAULT_ROOT, verify_broader_universe


def rebuild_manifest(root: str | Path = DEFAULT_ROOT) -> list[dict[str, object]]:
    """Validate every frozen dataset and rebuild manifest.json deterministically."""
    return verify_broader_universe(root)


def main() -> None:
    manifests = rebuild_manifest()
    print(f"RECOVERY MANIFEST REBUILT: datasets={len(manifests)}", flush=True)


if __name__ == "__main__":
    main()
