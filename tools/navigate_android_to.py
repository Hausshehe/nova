"""Generic semantic Android navigation helper for Nova.

This tool is deliberately app-agnostic. It searches the current UI hierarchy
for a human target, scrolls a real scrollable UI when the target is off-screen,
and activates the best current semantic match. Nova still chooses the target;
the tool never contains app-specific screen names or planner coordinates.
"""

import re
from difflib import SequenceMatcher

from tools.android_root import run_root
from tools.observe_android import observe_android


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

    # Generic normalization for common UI wording variations.
    # This is intentionally language-agnostic at the command level:
    # it helps "apps" match "app" without knowing anything about Android.
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
            # Also accept clear prefix relationships for words such as
            # "app"/"apps"/"application", without maintaining a synonym list.
            if len(target_word) >= 3 and len(label_word) >= 3:
                shorter, longer = sorted((target_word, label_word), key=len)
                if longer.startswith(shorter) and len(shorter) >= 3:
                    found = True
                    break
        if found:
            matched += 1

    return matched / len(target_words)


def _score(label, target):
    label_n = " ".join(str(label or "").lower().split())
    target_n = " ".join(str(target or "").lower().split())
    if not label_n or not target_n:
        return 0.0
    if label_n == target_n:
        return 100.0
    if target_n in label_n:
        return 90.0

    target_words = _words(target_n)
    label_words = _words(label_n)
    overlap = _semantic_word_overlap(target_words, label_words)
    if overlap == 1.0:
        return 85.0
    if overlap >= 0.5:
        return 60.0 + overlap * 20.0

    # Compare each target word with the closest current label word as a
    # fallback for normal linguistic variation, while avoiding weak matches.
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


def _find_match(nodes, target):
    candidates = []
    for node in nodes or []:
        if not isinstance(node, dict) or not node.get("enabled", True):
            continue
        label = _label(node)
        score = _score(label, target)
        if score >= 50.0:
            candidates.append((score, node, label))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0]


def _bounds_center(bounds):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    x1, y1, x2, y2 = map(int, match.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def _activate(node):
    center = _bounds_center(node.get("bounds", ""))
    if center is None:
        return False, "Matching node has invalid bounds."
    x, y = center
    result = run_root(f"input tap {x} {y}")
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "Tap failed").strip()
    return True, ""


def _scroll(direction):
    if direction == "up":
        command = "/system/bin/input swipe 540 300 540 700 350"
    else:
        command = "/system/bin/input swipe 540 700 540 300 350"
    result = run_root(command)
    return result.returncode == 0


def _ui_signature(observed):
    """Create a small position-independent signature for detecting scroll stalls."""
    state = observed.get("state") or {}
    visible = tuple(str(value).strip().lower() for value in state.get("visible_text", []) if str(value).strip())
    scrollable = tuple(
        str(item.get("bounds", ""))
        for item in state.get("scrollable", [])
        if isinstance(item, dict)
    )
    return visible, scrollable


def navigate_android_to(target, max_scrolls=8, direction="down"):
    """Find and activate a human-named UI target using adaptive semantic search.

    The helper checks the live hierarchy, scrolls only when the current UI is
    actually scrollable, re-observes after each scroll, detects when scrolling
    stops changing the screen, and reverses direction once when appropriate.
    It uses no app-specific names, aliases, or planner coordinates.
    """
    target = str(target or "").strip()
    if not target:
        return {"success": False, "verified": False, "message": "Target cannot be empty."}

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

    for phase_index, current_direction in enumerate(directions):
        phase_scrolls = 0
        previous_signature = None
        unchanged_count = 0

        while phase_scrolls <= budget:
            observed = observe_android(include_nodes=True)
            if not observed.get("success"):
                return {
                    "success": False,
                    "verified": False,
                    "target": target,
                    "scrolls": scrolls,
                    "message": observed.get("message", "UI observation failed."),
                }

            last_foreground = observed.get("foreground_package", "")
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

                verification = observe_android(include_nodes=False)
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
            previous_signature = signature

            # Two identical observations mean the requested direction is no
            # longer moving the list. Stop instead of repeatedly scrolling at
            # the end, then let the opposite direction search the other side.
            if unchanged_count >= 1:
                break

            if not _scroll(current_direction):
                break

            scrolls += 1
            phase_scrolls += 1

        # The second phase is the generic recovery route when the target was
        # above the starting viewport or the first direction reached an edge.
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
