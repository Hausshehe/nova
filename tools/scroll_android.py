"""Adaptive Android scrolling without app-specific navigation knowledge."""

import hashlib
import re
import time

from tools.android_root import run_root


DUMP_PATH = "/data/local/tmp/nova_scroll_probe.xml"
PROBE_TIMEOUT_SECONDS = 4
SCROLL_SETTLE_SECONDS = 0.75

# The scroll primitive remembers only traversal state, not app names, labels,
# coordinates, or destinations. This lets an agent sweep a scrollable screen
# in both directions instead of repeatedly issuing a no-op swipe at an edge.
_TRAVERSAL_DIRECTION = None
_BOUNDARY_STREAK = 0
_LAST_SIGNATURE = None


def _probe_signature():
    """Return a compact signature of the current UI hierarchy."""
    command = (
        f"/system/bin/uiautomator dump --compressed {DUMP_PATH} "
        f">/dev/null 2>&1 && cat {DUMP_PATH}"
    )
    result = run_root(command, timeout=PROBE_TIMEOUT_SECONDS)
    if result.returncode != 0 or not result.stdout:
        return None

    # Ignore bounds so ordinary content movement does not depend on generated
    # coordinates; the hierarchy/text structure is enough to detect a no-op.
    text = re.sub(r'\s+bounds="[^"]*"', "", result.stdout)
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()


def _swipe(direction):
    if direction == "down":
        command = "/system/bin/input swipe 540 700 540 300 500"
    else:
        command = "/system/bin/input swipe 540 300 540 700 500"
    return run_root(command)


def scroll_android(direction="down"):
    """Scroll adaptively, reversing direction when the current edge is reached.

    The caller still requests ``up`` or ``down`` normally. If repeated scrolling
    reaches a boundary, the primitive detects that the UI hierarchy stopped
    changing and reverses its traversal direction. No app, screen, target,
    coordinate, or Settings-specific knowledge is used here.
    """
    global _TRAVERSAL_DIRECTION, _BOUNDARY_STREAK, _LAST_SIGNATURE

    requested = str(direction or "down").strip().lower()
    if requested not in {"up", "down"}:
        return {
            "success": False,
            "verified": False,
            "message": "Direction must be 'up' or 'down'.",
        }

    before = _probe_signature()

    # Normally honor the requested direction. Once the requested direction has
    # hit an edge, continue the traversal in the opposite direction so a target
    # that was scrolled past can be recovered instead of looping at the edge.
    actual = requested
    if _TRAVERSAL_DIRECTION is None:
        _TRAVERSAL_DIRECTION = requested
    elif _BOUNDARY_STREAK >= 1 and requested == _TRAVERSAL_DIRECTION:
        _TRAVERSAL_DIRECTION = "up" if _TRAVERSAL_DIRECTION == "down" else "down"
        actual = _TRAVERSAL_DIRECTION
        _BOUNDARY_STREAK = 0
    else:
        actual = _TRAVERSAL_DIRECTION

    try:
        result = _swipe(actual)
        if result.returncode != 0:
            return {
                "success": False,
                "verified": False,
                "direction": actual,
                "requested_direction": requested,
                "message": (result.stderr or result.stdout or "Scroll failed").strip(),
            }

        # Android's Settings/RecyclerView and many other UIs animate the swipe.
        # Probe only after the animation settles; probing immediately can see the
        # old hierarchy and falsely conclude that we are already at an edge.
        time.sleep(SCROLL_SETTLE_SECONDS)
        after = _probe_signature()
        changed = before is None or after is None or before != after

        if changed:
            _BOUNDARY_STREAK = 0
            _LAST_SIGNATURE = after
        else:
            _BOUNDARY_STREAK += 1
            # A confirmed no-op is evidence of an edge. Flip immediately so the
            # next invocation traverses back through content already passed.
            _TRAVERSAL_DIRECTION = "up" if actual == "down" else "down"
            _LAST_SIGNATURE = after

        return {
            "success": True,
            "verified": bool(changed),
            "direction": actual,
            "requested_direction": requested,
            "boundary_detected": not changed,
            "reversed_for_boundary": actual != requested,
            "message": (
                "Scroll changed the current UI; observe it to choose the next action."
                if changed
                else "Scroll reached a UI boundary; traversal direction was reversed adaptively."
            ),
            "output": result.stdout.strip(),
        }
    except Exception as exc:
        return {
            "success": False,
            "verified": False,
            "direction": actual,
            "requested_direction": requested,
            "message": str(exc),
        }
