"""Read the latest live hierarchy published by NovaAccessibilityService."""

from __future__ import annotations

import json
import time

from tools.android_root import run_root

SNAPSHOT_PATHS = (
    "/data/user/0/com.infoney.nova/files/nova_accessibility_snapshot.json",
    "/data/data/com.infoney.nova/files/nova_accessibility_snapshot.json",
)
DEFAULT_MAX_AGE_SECONDS = 2.0


def read_accessibility_snapshot(max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS):
    """Return a fresh accessibility snapshot, or None when unavailable/stale."""
    now_ms = int(time.time() * 1000)
    max_age_ms = max(0, int(float(max_age_seconds) * 1000))

    for path in SNAPSHOT_PATHS:
        result = run_root(f"cat {path}", timeout=2)
        if result.returncode != 0 or not (result.stdout or "").strip():
            continue

        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            continue

        if data.get("source") != "accessibility_service":
            continue

        timestamp_ms = int(data.get("timestamp_ms") or 0)
        if timestamp_ms <= 0 or now_ms - timestamp_ms > max_age_ms:
            continue

        nodes = data.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            continue

        return data

    return None
