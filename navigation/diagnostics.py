"""Structured, opt-in diagnostics for Nova navigation.

Diagnostics never influence control flow. They record what Nova observed,
what action was attempted, how long it took, and what result was returned.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DiagnosticEvent:
    """One timestamped event in a Nova execution trace."""

    timestamp: float
    kind: str
    name: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


class DiagnosticTrace:
    """Collect an opt-in, JSON-safe execution timeline."""

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = bool(enabled)
        self.events: List[DiagnosticEvent] = []
        self._open_actions: Dict[str, float] = {}

    def record(self, kind: str, name: str = "", **data: Any) -> None:
        if not self.enabled:
            return
        self.events.append(
            DiagnosticEvent(
                timestamp=time.monotonic(),
                kind=str(kind),
                name=str(name),
                data=_json_safe(data),
            )
        )

    def start_action(self, action_id: str, name: str, **data: Any) -> None:
        if not self.enabled:
            return
        self._open_actions[action_id] = time.monotonic()
        self.record("action_start", name, action_id=action_id, **data)

    def end_action(self, action_id: str, name: str, **data: Any) -> None:
        if not self.enabled:
            return
        started = self._open_actions.pop(action_id, None)
        duration_ms = None if started is None else round((time.monotonic() - started) * 1000, 1)
        self.record("action_end", name, action_id=action_id, duration_ms=duration_ms, **data)

    def snapshot(self, *, name: str = "observation", **data: Any) -> None:
        self.record("observation", name, **data)

    def decision(self, name: str, **data: Any) -> None:
        self.record("decision", name, **data)

    def failure(self, name: str, **data: Any) -> None:
        self.record("failure", name, **data)

    def to_dict(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "events": []}
        base = self.events[0].timestamp if self.events else time.monotonic()
        return {
            "enabled": True,
            "events": [
                {
                    "t_ms": round((event.timestamp - base) * 1000, 1),
                    "kind": event.kind,
                    "name": event.name,
                    **event.data,
                }
                for event in self.events
            ],
        }

    def render(self) -> str:
        """Render a compact human-readable trace for Termux."""
        if not self.enabled:
            return "Diagnostics disabled."
        lines = ["=== NOVA TRACE ==="]
        for event in self.to_dict()["events"]:
            payload = {key: value for key, value in event.items() if key not in {"t_ms", "kind", "name"}}
            suffix = " " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) if payload else ""
            lines.append(f"{event['t_ms']:>8}ms {event['kind']:<14} {event['name']}{suffix}")
        return "\n".join(lines)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)
