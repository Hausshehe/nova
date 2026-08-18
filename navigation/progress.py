"""Generic progress measurement for adaptive Android scrolling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .state import ObservationQuality, ScreenSnapshot


@dataclass(frozen=True)
class Progress:
    changed: bool
    meaningful: bool
    new_text: Tuple[str, ...] = ()
    lost_text: Tuple[str, ...] = ()
    reason: str = ""


def compare_snapshots(before: ScreenSnapshot, after: ScreenSnapshot) -> Progress:
    """Determine whether a scroll produced evidence of meaningful UI progress."""
    if before.observation_quality is not ObservationQuality.VALID:
        return Progress(False, False, reason="Previous snapshot was not valid.")
    if after.observation_quality is not ObservationQuality.VALID:
        return Progress(False, False, reason="Current snapshot was not valid.")

    before_text = {text.strip().lower() for text in before.visible_text if text.strip()}
    after_text = {text.strip().lower() for text in after.visible_text if text.strip()}
    new_text = tuple(sorted(after_text - before_text))
    lost_text = tuple(sorted(before_text - after_text))

    signature_changed = before.semantic_signature() != after.semantic_signature()
    package_changed = before.foreground_package != after.foreground_package
    meaningful = bool(new_text or lost_text or signature_changed or package_changed)

    if package_changed:
        reason = "Foreground package changed."
    elif new_text or lost_text:
        reason = "Visible semantic text changed."
    elif signature_changed:
        reason = "Live node positions or structure changed."
    else:
        reason = "No meaningful UI change detected."

    return Progress(
        changed=signature_changed,
        meaningful=meaningful,
        new_text=new_text,
        lost_text=lost_text,
        reason=reason,
    )
