"""State primitives for Nova's adaptive Android navigation engine."""

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple


class ObservationQuality(str, Enum):
    """How trustworthy an Android UI observation is for navigation decisions."""

    VALID = "VALID"
    TRANSIENT = "TRANSIENT"
    FAILED = "FAILED"


class Resolution(str, Enum):
    """Outcome of resolving a logical target against a live screen."""

    FOUND = "FOUND"
    NOT_FOUND_YET = "NOT_FOUND_YET"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID_OBSERVATION = "INVALID_OBSERVATION"


@dataclass(frozen=True)
class ScreenSnapshot:
    """Immutable, navigation-facing representation of one UI observation."""

    foreground_package: str
    visible_nodes: Tuple[Dict[str, Any], ...] = ()
    actionable_nodes: Tuple[Dict[str, Any], ...] = ()
    scrollable_regions: Tuple[Dict[str, Any], ...] = ()
    visible_text: Tuple[str, ...] = ()
    timestamp: float = field(default_factory=monotonic)
    observation_quality: ObservationQuality = ObservationQuality.VALID
    message: str = ""

    @property
    def valid(self) -> bool:
        return self.observation_quality is ObservationQuality.VALID

    @property
    def failed(self) -> bool:
        return self.observation_quality is ObservationQuality.FAILED

    @property
    def scrollable(self) -> bool:
        return bool(self.scrollable_regions)

    def semantic_signature(self) -> Tuple[Any, ...]:
        """Return a stable-ish signature for progress comparison.

        Bounds are retained because position changes are meaningful evidence of
        scrolling, while the collection remains independent of device pixels.
        """
        node_signature = tuple(
            (
                str(node.get("text", "")).strip().lower(),
                str(node.get("content_description", "")).strip().lower(),
                str(node.get("resource_id", "")).strip().lower(),
                str(node.get("bounds", "")),
            )
            for node in self.visible_nodes
            if isinstance(node, dict)
        )
        scroll_signature = tuple(
            str(region.get("bounds", ""))
            for region in self.scrollable_regions
            if isinstance(region, dict)
        )
        return (self.foreground_package, node_signature, scroll_signature)


def snapshot_from_observation(observed: Dict[str, Any]) -> ScreenSnapshot:
    """Convert the existing observe_android result into the new abstraction."""
    if not isinstance(observed, dict):
        return ScreenSnapshot(
            foreground_package="",
            observation_quality=ObservationQuality.FAILED,
            message="Observation result was not a mapping.",
        )

    quality_name = str(observed.get("observation_quality", "")).upper()
    if quality_name in ObservationQuality.__members__:
        quality = ObservationQuality[quality_name]
    elif observed.get("success"):
        quality = ObservationQuality.VALID
    else:
        quality = ObservationQuality.FAILED

    state = observed.get("state") or {}
    nodes = observed.get("nodes") or ()
    interactive = state.get("interactive") or ()
    scrollable = state.get("scrollable") or ()
    visible_text = state.get("visible_text") or ()

    return ScreenSnapshot(
        foreground_package=str(observed.get("foreground_package", "")),
        visible_nodes=tuple(node for node in nodes if isinstance(node, dict)),
        actionable_nodes=tuple(node for node in interactive if isinstance(node, dict)),
        scrollable_regions=tuple(item for item in scrollable if isinstance(item, dict)),
        visible_text=tuple(str(value) for value in visible_text if str(value).strip()),
        observation_quality=quality,
        message=str(observed.get("message", "")),
    )
