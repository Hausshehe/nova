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



def _wrap(name, function):
    def wrapped(*args, **kwargs):
        started = _stamp()
        _log(f"START {name}")
        try:
            result = function(*args, **kwargs)
            elapsed = _stamp() - started
            _log(f"END   {name} ({elapsed:.2f}s) result={_compact(result)}")
            return result
        except BaseException as exc:
            elapsed = _stamp() - started
            _log(f"FAIL  {name} ({elapsed:.2f}s) {type(exc).__name__}: {exc}")
            raise

    return wrapped



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
        result = function(*args, **kwargs)
        elapsed = _stamp() - started
        state = result.get("state") or {}
        visible = state.get("visible_text") or []
        _log(
            "OBSERVE "
            f"{elapsed:.2f}s success={result.get('success')} "
            f"verified={result.get('verified')} "
            f"pkg={result.get('foreground_package', '')} "
            f"nodes={result.get('node_count', 0)} "
            f"scrollable={bool(state.get('scrollable'))} "
            f"visible={list(visible)[:8]}"
        )
        return result

    return wrapped



def _wrap_find_match(function):
    def wrapped(nodes, target):
        started = _stamp()
        result = function(nodes, target)
        elapsed = _stamp() - started
        _log(f"MATCH target={target!r} ({elapsed:.3f}s) -> {_compact(result)}")
        return result

    return wrapped



def _wrap_handoff(function):
    def wrapped(nodes):
        started = _stamp()
        result = function(nodes)
        elapsed = _stamp() - started
        _log(f"HANDOFF ({elapsed:.3f}s) -> {_compact(result)}")
        return result

    return wrapped



def _wrap_target_app(function):
    def wrapped(target):
        started = _stamp()
        result = function(target)
        elapsed = _stamp() - started
        _log(f"TARGET-IS-APP target={target!r} ({elapsed:.2f}s) -> {result}")
        return result

    return wrapped



def _wrap_activate(function):
    def wrapped(node):
        label = navigator._label(node)
        started = _stamp()
        _log(f"TAP START label={label!r} bounds={node.get('bounds', '')!r}")
        result = function(node)
        elapsed = _stamp() - started
        _log(f"TAP END   label={label!r} ({elapsed:.2f}s) -> {_compact(result)}")
        return result

    return wrapped



def _wrap_scroll(function):
    def wrapped(direction):
        started = _stamp()
        _log(f"SCROLL START direction={direction}")
        result = function(direction)
        elapsed = _stamp() - started
        _log(f"SCROLL END   direction={direction} ({elapsed:.2f}s) -> {result}")
        return result

    return wrapped



def install_wrappers():
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
