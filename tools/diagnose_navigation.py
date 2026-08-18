"""Trace Nova Android navigation without changing navigator behavior.

This diagnostic wraps the existing navigation primitives at runtime and prints
step boundaries, durations, and key decisions. It is intentionally separate
from production navigation logic so the normal agent remains unchanged.
"""

import sys
import time

import nova_agent
import tools.navigate_android_to as navigator


def _stamp():
    return time.monotonic()


def _log(message):
    print(f"[NOVA-NAV-DIAG] {message}", flush=True)


def _compact(value):
    if isinstance(value, dict):
        keys = (
            "success",
            "verified",
            "target",
            "matched_label",
            "match_score",
            "scrolls",
            "foreground_package",
            "message",
        )
        return {key: value.get(key) for key in keys if key in value}
    if isinstance(value, tuple) and len(value) >= 3:
        return {"score": round(float(value[0]), 1), "label": value[2]}
    if isinstance(value, bool):
        return value
    return type(value).__name__


def _wrap_observe(function):
    def wrapped(*args, **kwargs):
        started = _stamp()
        try:
            result = function(*args, **kwargs)
        except BaseException as exc:
            _log(f"OBSERVE FAIL ({_stamp() - started:.2f}s) {type(exc).__name__}: {exc}")
            raise

        elapsed = _stamp() - started
        state = result.get("state") or {}
        scrollable = state.get("scrollable") or []
        visible = state.get("visible_text") or []
        regions = [
            item.get("bounds", "")
            for item in scrollable
            if isinstance(item, dict) and item.get("bounds")
        ]
        _log(
            "OBSERVE "
            f"{elapsed:.2f}s success={result.get('success')} "
            f"verified={result.get('verified')} "
            f"pkg={result.get('foreground_package', '')} "
            f"nodes={result.get('node_count', 0)} "
            f"scrollable_count={len(scrollable)} "
            f"scrollable_bounds={regions[:4]} "
            f"visible={list(visible)[:8]}"
        )
        return result

    return wrapped


def _wrap_find_match(function):
    def wrapped(nodes, target):
        started = _stamp()
        result = function(nodes, target)
        _log(f"MATCH target={target!r} ({_stamp() - started:.3f}s) -> {_compact(result)}")
        return result

    return wrapped


def _wrap_handoff(function):
    def wrapped(nodes):
        started = _stamp()
        result = function(nodes)
        _log(f"HANDOFF ({_stamp() - started:.3f}s) -> {_compact(result)}")
        if result:
            _score, node, label = result
            ancestor = node.get("actionable_ancestor") if isinstance(node, dict) else None
            _log(
                f"HANDOFF NODE label={label!r} clickable={node.get('clickable')} "
                f"bounds={node.get('bounds','')!r} "
                f"ancestor_clickable={bool(isinstance(ancestor, dict) and ancestor.get('clickable'))} "
                f"ancestor_bounds={ancestor.get('bounds','')!r}" if isinstance(ancestor, dict)
                else f"HANDOFF NODE label={label!r} clickable={node.get('clickable')} bounds={node.get('bounds','')!r} ancestor=None"
            )
        return result

    return wrapped


def _wrap_target_app(function):
    def wrapped(target):
        started = _stamp()
        result = function(target)
        _log(f"TARGET-IS-APP target={target!r} ({_stamp() - started:.2f}s) -> {result}")
        return result

    return wrapped


def _wrap_activate(function):
    def wrapped(node):
        label = navigator._label(node)
        ancestor = node.get("actionable_ancestor") if isinstance(node, dict) else None
        started = _stamp()
        _log(
            f"TAP START label={label!r} node_clickable={node.get('clickable')} "
            f"node_bounds={node.get('bounds','')!r} "
            f"ancestor_bounds={ancestor.get('bounds','')!r}" if isinstance(ancestor, dict)
            else f"TAP START label={label!r} node_clickable={node.get('clickable')} node_bounds={node.get('bounds','')!r} ancestor=None"
        )
        result = function(node)
        _log(f"TAP END   label={label!r} ({_stamp() - started:.2f}s) -> {_compact(result)}")
        return result

    return wrapped


def _wrap_scroll(function):
    def wrapped(direction, scrollable=None):
        started = _stamp()
        regions = scrollable or []
        bounds = [
            item.get("bounds", "")
            for item in regions
            if isinstance(item, dict) and item.get("bounds")
        ]
        _log(f"SCROLL START direction={direction} regions={bounds[:4]}")
        result = function(direction, scrollable)
        _log(f"SCROLL END   direction={direction} ({_stamp() - started:.2f}s) -> {result}")
        return result

    return wrapped


def _wrap_run_root(function):
    def wrapped(command, timeout=None):
        text = str(command or "").strip().replace("\n", " ")
        interesting = (
            "uiautomator" in text
            or "input tap" in text
            or "input swipe" in text
            or "dumpsys activity" in text
        )
        if not interesting:
            return function(command, timeout=timeout) if timeout is not None else function(command)

        started = _stamp()
        result = function(command, timeout=timeout) if timeout is not None else function(command)
        _log(
            f"ROOT ({_stamp() - started:.2f}s) rc={result.returncode} "
            f"cmd={text[:180]!r}"
        )
        return result

    return wrapped


def install_wrappers():
    # run_root is imported into both navigator and observer modules, so wrap
    # each module-local reference to capture the actual primitive used.
    wrapped_root = _wrap_run_root(navigator.run_root)
    navigator.run_root = wrapped_root
    import tools.observe_android as observer
    observer.run_root = wrapped_root

    navigator.observe_android = _wrap_observe(navigator.observe_android)
    navigator._find_match = _wrap_find_match(navigator._find_match)
    navigator._find_app_collection_handoff = _wrap_handoff(
        navigator._find_app_collection_handoff
    )
    navigator._target_is_installed_app = _wrap_target_app(
        navigator._target_is_installed_app
    )
    navigator._activate = _wrap_activate(navigator._activate)
    navigator._scroll = _wrap_scroll(navigator._scroll)

    # nova_agent already imported navigate_android_to directly, so replace that
    # reference with the navigator module's now-instrumented implementation.
    nova_agent.navigate_android_to = navigator.navigate_android_to


def main():
    install_wrappers()
    goal = "Open Settings and open Apps, then open YouTube"
    if len(sys.argv) > 1:
        goal = " ".join(sys.argv[1:])

    _log(f"GOAL {goal!r}")
    started = _stamp()
    try:
        result = nova_agent.run_agent(goal)
        elapsed = _stamp() - started
        _log(f"RUN COMPLETE ({elapsed:.2f}s)")
        print(result)
        return 0 if isinstance(result, dict) and result.get("success") else 1
    except KeyboardInterrupt:
        elapsed = _stamp() - started
        _log(f"INTERRUPTED ({elapsed:.2f}s)")
        raise
    except BaseException as exc:
        elapsed = _stamp() - started
        _log(f"RUN FAILED ({elapsed:.2f}s) {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
