"""Verified navigation checkpoints for resumable multi-step goals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .state import ObservationQuality, ScreenSnapshot


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

    def matches_current(self, snapshot: Optional[ScreenSnapshot], *, min_text_overlap: float = 0.60) -> bool:
        """Conservatively decide whether the phone still resembles the last checkpoint."""
        latest = self.latest
        if latest is None or snapshot is None:
            return False
        if snapshot.observation_quality is not ObservationQuality.VALID:
            return False
        if snapshot.foreground_package != latest.foreground_package:
            return False

        expected = {text.strip().lower() for text in latest.snapshot.visible_text if text.strip()}
        current = {text.strip().lower() for text in snapshot.visible_text if text.strip()}
        if not expected or not current:
            return snapshot.foreground_package == latest.foreground_package

        overlap = len(expected & current) / len(expected | current)
        return overlap >= max(0.0, min(float(min_text_overlap), 1.0))
