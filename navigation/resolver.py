"""Context-aware semantic target resolution for Nova."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, Optional, Tuple

from .state import Resolution, ScreenSnapshot


@dataclass(frozen=True)
class TargetMatch:
    """A semantic match resolved against the current live screen."""

    resolution: Resolution
    target: str
    node: Optional[Dict[str, Any]] = None
    label: str = ""
    score: float = 0.0
    reason: str = ""


def _label(node: Dict[str, Any]) -> str:
    return (
        str(node.get("text") or "").strip()
        or str(node.get("content_description") or "").strip()
        or str(node.get("resource_id") or "").strip()
    )


def _normalize_word(word: str) -> str:
    word = str(word or "").lower().strip()
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _words(value: str) -> set[str]:
    return {
        normalized
        for word in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if (normalized := _normalize_word(word))
    }


def _semantic_score(label: str, target: str, node: Dict[str, Any]) -> float:
    label_n = " ".join(str(label or "").lower().split())
    target_n = " ".join(str(target or "").lower().split())
    if not label_n or not target_n:
        return 0.0
    if label_n == target_n:
        return 100.0

    target_words = _words(target_n)
    label_words = _words(label_n)
    if not target_words or not label_words:
        return SequenceMatcher(None, target_n, label_n).ratio() * 50.0

    overlap = len(target_words & label_words) / len(target_words)
    if overlap == 1.0:
        ratio = SequenceMatcher(None, target_n, label_n).ratio()
        extras = max(0, len(label_words - target_words))
        return 78.0 + ratio * 7.0 - extras * 3.0 + (1.5 if node.get("clickable") else 0.0)
    if overlap >= 0.5:
        return 55.0 + overlap * 20.0

    similarities = []
    for target_word in target_words:
        best = max(
            SequenceMatcher(None, target_word, label_word).ratio()
            for label_word in label_words
        )
        similarities.append(best)
    average = sum(similarities) / len(similarities)
    return 45.0 + average * 30.0 if average >= 0.72 else SequenceMatcher(None, target_n, label_n).ratio() * 50.0


def _tiebreak(label: str, target: str, node: Dict[str, Any]) -> Tuple[Any, ...]:
    target_words = _words(target)
    label_words = _words(label)
    ratio = SequenceMatcher(None, str(target).lower(), str(label).lower()).ratio()
    return (
        1 if node.get("clickable") else 0,
        -max(0, len(label_words - target_words)),
        ratio,
        -len(label_words),
        -len(label),
    )


def _iter_nodes(snapshot: ScreenSnapshot) -> Iterable[Dict[str, Any]]:
    for node in snapshot.visible_nodes:
        if isinstance(node, dict) and node.get("enabled", True):
            yield node


def _best_ui_match(snapshot: ScreenSnapshot, target: str) -> Optional[TargetMatch]:
    candidates = []
    for node in _iter_nodes(snapshot):
        label = _label(node)
        score = _semantic_score(label, target, node)
        if score >= 50.0:
            candidates.append((score, _tiebreak(label, target, node), node, label))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    score, _, node, label = candidates[0]
    return TargetMatch(
        resolution=Resolution.FOUND,
        target=target,
        node=node,
        label=label,
        score=score,
        reason="Semantic match found in the current live hierarchy.",
    )


def resolve_target(
    snapshot: ScreenSnapshot,
    target: str,
    *,
    installed_packages: Optional[Iterable[str]] = None,
) -> TargetMatch:
    """Resolve a target using screen context before installed-app identity.

    A logical target is first interpreted as something represented by the
    current screen. Installed-package information is only a fallback signal,
    preventing generic labels such as ``Apps`` from being reclassified as an
    installed application merely because package inventory happens to contain
    a loose match.
    """
    target = " ".join(str(target or "").split())
    if not target:
        return TargetMatch(Resolution.INVALID_OBSERVATION, target, reason="Target is empty.")
    if snapshot.observation_quality is not snapshot.observation_quality.VALID:
        return TargetMatch(
            Resolution.INVALID_OBSERVATION,
            target,
            reason="The current screen observation is not valid for resolution.",
        )

    direct = _best_ui_match(snapshot, target)
    if direct is not None:
        return direct

    package_names = {str(package).strip().lower() for package in (installed_packages or ()) if str(package).strip()}
    target_words = _words(target)
    package_match = any(
        target.lower() == package.rsplit(".", 1)[-1].replace("_", " ")
        or target.lower().replace(" ", "") in package.replace(".", "")
        for package in package_names
    )
    if package_match and snapshot.scrollable:
        return TargetMatch(
            Resolution.NOT_FOUND_YET,
            target,
            reason="Target is consistent with installed-app identity but is not visible yet.",
        )

    return TargetMatch(
        Resolution.NOT_FOUND_YET,
        target,
        reason="No sufficiently strong semantic match is visible on the current screen.",
    )
