"""Generic semantic Android navigation helper for Nova.

This tool is deliberately app-agnostic. It searches the current UI hierarchy
for a human target, scrolls a real scrollable UI when the target is off-screen,
and activates the best current semantic match. Nova still chooses the target;
the tool never contains app-specific screen names or planner coordinates.
"""

import re
import time
from difflib import SequenceMatcher

from tools.android_root import run_root
from tools.find_android_app import find_android_app
from tools.observe_android import observe_android


RECOVERY_DELAY_SECONDS = 0.20
MAX_SCROLL_RECOVERY_ATTEMPTS = 1


def _label(node):
    return (
        (node.get("text") or "").strip()
        or (node.get("content_description") or "").strip()
        or (node.get("resource_id") or "").strip()
    )


def _normalize_word(word):
    word = str(word or "").lower().strip()
    if not word:
        return ""

    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]

    return word


def _words(value):
    return {
        normalized
        for word in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if (normalized := _normalize_word(word))
    }


def _word_forms(word):
    """Return lightweight morphology variants without app-specific synonyms."""
    word = str(word or "").lower().strip()
    forms = {word}
    if len(word) > 3 and word.endswith("s"):
        forms.add(word[:-1])
    if len(word) > 4 and word.endswith("es"):
        forms.add(word[:-2])
    if len(word) > 5 and word.endswith("ies"):
        forms.add(word[:-3] + "y")
    return forms


def _semantic_word_overlap(target_words, label_words):
    """Score target words against current UI words using generic morphology."""
    if not target_words:
        return 0.0

    matched = 0
    for target_word in target_words:
        target_forms = _word_forms(target_word)
        found = False
        for label_word in label_words:
            label_forms = _word_forms(label_word)
            if target_forms & label_forms:
                found = True
                break
            if len(target_word) >= 3 and len(label_word) >= 3:
                shorter, longer = sorted((target_word, label_word), key=len)
                if longer.startswith(shorter) and len(shorter) >= 3:
                    found = True
                    break
        if found:
            matched += 1

    return matched / len(target_words)


def _score(label, target, node=None):
    label_n = " ".join(str(label or "").lower().split())
    target_n = " ".join(str(target or "").lower().split())
    if not label_n or not target_n:
        return 0.0
    if label_n == target_n:
        return 100.0

    target_words = _words(target_n)
    label_words = _words(label_n)
    overlap = _semantic_word_overlap(target_words, label_words)

    if overlap == 1.0:
        target_ratio = SequenceMatcher(None, target_n, label_n).ratio()
        extras = max(0, len(label_words - target_words))
        score = 78.0 + (target_ratio * 7.0) - (extras * 3.0)
        if node and node.get("clickable"):
            score += 1.5
        return score
    if overlap >= 0.5:
        return 55.0 + overlap * 20.0

    if target_words and label_words:
        similarities = []
        for target_word in target_words:
            best = max(
                SequenceMatcher(None, target_word, label_word).ratio()
                for label_word in label_words
            )
            similarities.append(best)
        average = sum(similarities) / len(similarities)
        if average >= 0.72:
            return 45.0 + average * 30.0

    return SequenceMatcher(None, target_n, label_n).ratio() * 50.0


def _candidate_tiebreak(label, target, node=None):
    """Prefer the closest semantic label and an actionable UI node on ties."""
    target_words = _words(target)
    label_words = _words(label)
    extra_words = max(0, len(label_words - target_words))
    target_n = " ".join(str(target or "").lower().split())
    label_n = " ".join(str(label or "").lower().split())
    ratio = SequenceMatcher(None, target_n, label_n).ratio()
    clickable = 1 if node and node.get("clickable") else 0
    return (clickable, -extra_words, ratio, -len(label_words), -len(label_n))


def _find_match(nodes, target):
    candidates = []
    for node in nodes or []:
        if not isinstance(node, dict) or not node.get("enabled", True):
            continue
        label = _label(node)
        score = _score(label, target, node)
        if score >= 50.0:
            candidates.append((score, _candidate_tiebreak(label, target, node), node, label))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    score, _, node, label = candidates[0]
    return score, node, label


def _find_app_collection_handoff(nodes):
    """Find a generic app-collection entry before searching for an app."""
    candidates = []
    collection_words = {"list", "browse", "installed", "all"}
    app_words = {"app", "application"}
    action_words = {"update", "upgrade", "restore", "backup"}

    for node in nodes or []:
        if not isinstance(node, dict) or not node.get("enabled", True):
            continue

        label = _label(node)
        words = _words(label)
        if not words:
            continue

        app_score = len(words & app_words)
        collection_score = len(words & collection_words)
        action_score = len(words & action_words)
        if not app_score or not collection_score:
            continue

        score = (app_score * 5) + (collection_score * 12) - (action_score * 20)
        score += SequenceMatcher(None, "app list", label.lower()).ratio() * 3

        if node.get("clickable"):
            score += 2
        elif node.get("focusable") or node.get("bounds"):
            score += 0.5
        else:
            continue

        candidates.append((score, _candidate_tiebreak(label, "app list", node), node, label))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    score, _, node, label = candidates[0]
    return score, node, label


def _target_is_installed_app(target):
    """Use the live package inventory to distinguish an app target generically."""
    result = find_android_app(target)
    return bool(result.get("success") and result.get("packages"))


def _bounds_center(bounds):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    x1, y1, x2, y2 = map(int, match.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def _bounds_rect(bounds):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    return tuple(map(int, match.groups()))


def _activate(node):
    """Activate a semantic node using its nearest live actionable ancestor."""
    candidate = node
    if not node.get("clickable"):
        ancestor = node.get("actionable_ancestor")
        if isinstance(ancestor, dict) and ancestor.get("enabled", True):
            candidate = ancestor

    center = _bounds_center(candidate.get("bounds", ""))
    if center is None:
        return False, "Matching node has invalid bounds."
    x, y = center
    result = run_root(f"input tap {x} {y}")
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "Tap failed").strip()
    return True, ""


def _scroll(direction, scrollable=None):
    """Scroll inside the live scrollable region reported by the UI hierarchy."""
    regions = [item for item in (scrollable or []) if isinstance(item, dict)]
    regions.sort(
        key=lambda item: (_bounds_rect(item.get("bounds", "")) or (0, 0, 0, 0)),
        reverse=True,
    )

    rect = _bounds_rect(regions[0].get("bounds", "")) if regions else None
    if rect is None:
        return False

    x1, y1, x2, y2 = rect
    width = x2 - x1
    height = y2 - y1
    if width < 80 or height < 160:
        return False

    x = max(x1 + 10, min(x2 - 10, (x1 + x2) // 2))
    top = y1 + max(10, int(height * 0.25))
    bottom = y1 + min(height - 10, int(height * 0.75))

    if direction == "up":
        start_y, end_y = top, bottom
    else:
        start_y, end_y = bottom, top

    command = f"/system/bin/input swipe {x} {start_y} {x} {end_y} 350"
    result = run_root(command)
    return result.returncode == 0


def _ui_signature(observed):
    """Create a position-independent signature for detecting scroll progress."""
    state = observed.get("state") or {}
    visible = tuple(str(value).strip().lower() for value in state.get("visible_text", []) if str(value).strip())
    scrollable = tuple(
        str(item.get("bounds", ""))
        for item in state.get("scrollable", [])
        if isinstance(item, dict)
    )
    return visible, scrollable


def _split_target_path(target):
    """Split a natural-language target chain into sequential destinations."""
    text = re.sub(r"\s+", " ", str(target or "").strip())
    if not text:
        return []

    parts = re.split(
        r"\s+(?:and|then)\s+(?:open|launch|start)\s+",
        text,
        flags=re.IGNORECASE,
    )
    return [part.strip(" ,") for part in parts if part.strip(" ,")]


def _observe_with_recovery(include_nodes=True):
    """Observe the live UI and retry once when a transient result is unusable."""
    observed = observe_android(include_nodes=include_nodes)
    if observed.get("success"):
        return observed

    time.sleep(RECOVERY_DELAY_SECONDS)
    return observe_android(include_nodes=include_nodes)


def _navigate_single_target(target, max_scrolls=8, direction="down"):
    """Navigate to one destination using the live hierarchy."""
    try:
        budget = max(0, min(int(max_scrolls), 12))
    except (TypeError, ValueError):
        budget = 8

    initial_direction = str(direction or "down").strip().lower()
    if initial_direction not in {"up", "down"}:
        initial_direction = "down"

    directions = [initial_direction, "up" if initial_direction == "down" else "down"]
    scrolls = 0
    last_foreground = ""
    handoff_used = False
    target_is_app = _target_is_installed_app(target)

    for phase_index, current_direction in enumerate(directions):
        phase_scrolls = 0
        previous_signature = None
        unchanged_count = 0
        recovery_attempts = 0

        while phase_scrolls <= budget:
            observed = _observe_with_recovery(include_nodes=True)
            if not observed.get("success"):
                return {
                    "success": False,
                    "verified": False,
                    "target": target,
                    "scrolls": scrolls,
                    "message": observed.get("message", "UI observation failed."),
                }

            last_foreground = observed.get("foreground_package", "")

            if target_is_app and not handoff_used:
                handoff = _find_app_collection_handoff(observed.get("nodes"))
                if handoff:
                    _, node, label = handoff
                    activated, error = _activate(node)
                    if not activated:
                        return {
                            "success": False,
                            "verified": False,
                            "target": target,
                            "matched_label": label,
                            "scrolls": scrolls,
                            "message": error,
                        }
                    handoff_used = True
                    previous_signature = None
                    unchanged_count = 0
                    recovery_attempts = 0
                    time.sleep(RECOVERY_DELAY_SECONDS)
                    continue

            match = _find_match(observed.get("nodes"), target)
            if match:
                score, node, label = match
                activated, error = _activate(node)
                if not activated:
                    return {
                        "success": False,
                        "verified": False,
                        "target": target,
                        "matched_label": label,
                        "scrolls": scrolls,
                        "message": error,
                    }

                verification = _observe_with_recovery(include_nodes=False)
                return {
                    "success": True,
                    "verified": bool(verification.get("success")),
                    "target": target,
                    "matched_label": label,
                    "match_score": round(score, 1),
                    "scrolls": scrolls,
                    "foreground_package": verification.get("foreground_package", last_foreground),
                    "message": "Target found and activated using the current UI hierarchy.",
                }

            state = observed.get("state") or {}
            if not state.get("scrollable") or phase_scrolls >= budget:
                break

            signature = _ui_signature(observed)
            if signature == previous_signature:
                unchanged_count += 1
            else:
                unchanged_count = 0
                recovery_attempts = 0
            previous_signature = signature

            if unchanged_count >= 2:
                if recovery_attempts < MAX_SCROLL_RECOVERY_ATTEMPTS:
                    recovery_attempts += 1
                    time.sleep(RECOVERY_DELAY_SECONDS)
                    retry = _observe_with_recovery(include_nodes=True)
                    if retry.get("success"):
                        retry_signature = _ui_signature(retry)
                        last_foreground = retry.get("foreground_package", last_foreground)
                        if retry_signature != signature:
                            previous_signature = retry_signature
                            unchanged_count = 0
                            recovery_attempts = 0
                            observed = retry
                            continue

                        retry_state = retry.get("state") or {}
                        if retry_state.get("scrollable") and _scroll(current_direction, retry_state.get("scrollable")):
                            scrolls += 1
                            phase_scrolls += 1
                            unchanged_count = 0
                            continue
                break

            if not _scroll(current_direction, state.get("scrollable")):
                if recovery_attempts < MAX_SCROLL_RECOVERY_ATTEMPTS:
                    recovery_attempts += 1
                    time.sleep(RECOVERY_DELAY_SECONDS)
                    refreshed = _observe_with_recovery(include_nodes=True)
                    refreshed_state = refreshed.get("state") or {}
                    if refreshed.get("success") and refreshed_state.get("scrollable"):
                        if _scroll(current_direction, refreshed_state.get("scrollable")):
                            scrolls += 1
                            phase_scrolls += 1
                            recovery_attempts = 0
                            continue
                break

            scrolls += 1
            phase_scrolls += 1

        if phase_index == 0 and len(directions) > 1:
            continue
        break

    return {
        "success": False,
        "verified": True,
        "target": target,
        "scrolls": scrolls,
        "foreground_package": last_foreground,
        "message": "Target was not found after adaptive semantic search in both directions.",
    }


def navigate_android_to(target, max_scrolls=8, direction="down"):
    """Find and activate one or more human-named UI targets sequentially."""
    targets = _split_target_path(target)
    if not targets:
        return {"success": False, "verified": False, "message": "Target cannot be empty."}

    total_scrolls = 0
    completed = []

    for current_target in targets:
        result = _navigate_single_target(current_target, max_scrolls=max_scrolls, direction=direction)
        total_scrolls += int(result.get("scrolls", 0))

        if not result.get("success") or not result.get("verified"):
            return {
                "success": False,
                "verified": bool(result.get("verified")),
                "target": target,
                "completed_targets": completed,
                "failed_target": current_target,
                "scrolls": total_scrolls,
                "foreground_package": result.get("foreground_package", ""),
                "message": result.get("message", f"Could not complete navigation to '{current_target}'."),
            }

        completed.append({
            "target": current_target,
            "matched_label": result.get("matched_label", ""),
            "match_score": result.get("match_score", 0),
        })

    return {
        "success": True,
        "verified": True,
        "target": target,
        "completed_targets": completed,
        "scrolls": total_scrolls,
        "foreground_package": result.get("foreground_package", ""),
        "message": "All navigation targets were found and activated sequentially using the live UI hierarchy.",
    }
