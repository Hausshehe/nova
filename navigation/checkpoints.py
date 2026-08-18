"""Verified navigation checkpoints for resumable multi-step goals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .state import ScreenSnapshot


@dataclass(frozen=True)
class Checkpoint:
    """Last known-good boundary in a navigation plan."""

    index: int
    target: str
    snapshot: ScreenSnapshot
    foreground_package: str
    verified: bool = True


@dataclass
class CheckpointStore:
    """Bounded in-memory checkpoint history for one navigation attempt."""

    max_entries: int = 16
    _items: List[Checkpoint] = field(default_factory=list)

    def save(self, checkpoint: Checkpoint) -> None:
        if not checkpoint.verified:
            return
        self._items.append(checkpoint)
        if len(self._items) > max(1, int(self.max_entries)):
            del self._items[: len(self._items) - int(self.max_entries)]

    @property
    def latest(self) -> Optional[Checkpoint]:
        return self._items[-1] if self._items else None

    @property
    def items(self) -> Tuple[Checkpoint, ...]:
        return tuple(self._items)

    def resume_snapshot(self) -> Optional[ScreenSnapshot]:
        latest = self.latest
        return latest.snapshot if latest else None
