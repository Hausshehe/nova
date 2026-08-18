"""Structured, non-invasive diagnostics for navigation experiments."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DiagnosticTrace:
    """Collect ordered evidence without changing navigation decisions."""

    started: float = field(default_factory=time.monotonic)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def record(self, stage: str, event: str, **data: Any) -> None:
        now = time.monotonic()
        self.events.append(
            {
                "stage": stage,
                "event": event,
                "elapsed_ms": round((now - self.started) * 1000, 1),
                **data,
            }
        )

    def as_dict(self) -> Dict[str, Any]:
        return {"events": list(self.events)}

    def json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False, sort_keys=True)
